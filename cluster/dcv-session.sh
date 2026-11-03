#!/usr/bin/env bash
# Opens the login node's DCV desktop in the browser through Session Manager, never the
# internet: cluster.yaml closes the DCV port to the world, so the desktop is reached at
# https://localhost:8443 through a port forward that AWS authenticates. With a certificate
# the browser already trusts (mkcert makes one for localhost) the page shows a padlock:
# the certificate and its key are put on the node first, and DCV restarted to read them.
# usage: dcv-session.sh [-c cert.pem -k cert.key] [cluster]
# Needs the AWS CLI with the Session Manager plugin; no key pair and no open port.
set -euo pipefail
cert='' key=''
while getopts 'c:k:' option; do
  case $option in
    c) cert=$OPTARG ;;
    k) key=$OPTARG ;;
    *) exit 2 ;;
  esac
done
shift $((OPTIND - 1))
cluster=${1:-qec} region=${AWS_REGION:-us-east-2} port=8443
[[ -z $cert$key || ( -n $cert && -n $key ) ]] || { echo "give both -c and -k, or neither" >&2; exit 2; }
node=$(aws ec2 describe-instances --region "$region" \
  --filters "Name=tag:parallelcluster:cluster-name,Values=$cluster" \
    Name=tag:parallelcluster:node-type,Values=LoginNode Name=instance-state-name,Values=running \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
[[ -n $node && $node != None ]] || { echo "no login node is running in cluster $cluster" >&2; exit 1; }
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# Runs a script on the node as root through Session Manager and prints what it wrote.
on_node() {
  local command state
  jq -n --arg script "$1" '{commands: [$script]}' > "$work/params.json"
  command=$(aws ssm send-command --region "$region" --document-name AWS-RunShellScript \
    --instance-ids "$node" --query Command.CommandId --output text --parameters "file://$work/params.json")
  for _ in $(seq 1 40); do
    state=$(aws ssm get-command-invocation --region "$region" --command-id "$command" \
      --instance-id "$node" --query Status --output text 2>/dev/null || true)
    [[ $state == Pending || $state == InProgress || -z $state ]] || break
    sleep 3
  done
  [[ $state == Success ]] || { echo "the node did not finish: $state" >&2; exit 1; }
  aws ssm get-command-invocation --region "$region" --command-id "$command" \
    --instance-id "$node" --query StandardOutputContent --output text
}

if [[ -n $cert ]]; then
  on_node "$(printf 'cat > /etc/dcv/dcv.pem <<"PEM"\n%s\nPEM\ncat > /etc/dcv/dcv.key <<"PEM"\n%s\nPEM\n' \
    "$(cat "$cert")" "$(cat "$key")")
chown dcv:dcv /etc/dcv/dcv.pem /etc/dcv/dcv.key && chmod 640 /etc/dcv/dcv.pem /etc/dcv/dcv.key
systemctl restart dcvserver" > /dev/null
fi

# The forward is up before the token is minted: the token lives thirty seconds.
aws ssm start-session --region "$region" --target "$node" --document-name AWS-StartPortForwardingSession \
  --parameters "portNumber=$port,localPortNumber=$port" &
forward=$!
# ParallelCluster's own connect script, the one pcluster dcv-connect runs over SSH, makes
# or reuses the user's session and prints a one-time token for it.
read -r _ session token < <(on_node 'runuser -u ubuntu -- /opt/parallelcluster/scripts/pcluster_dcv_connect.sh /home/ubuntu' \
  | sed -n 's/^PclusterDcvServerPort=\([0-9]*\) PclusterDcvSessionId=\([^ ]*\) PclusterDcvSessionToken=\([^ ]*\).*/\1 \2 \3/p')
[[ -n ${token:-} ]] || { kill "$forward" 2>/dev/null; echo "the node gave no session token" >&2; exit 1; }
url="https://localhost:$port?authToken=$token#$session"
echo "$url"
open "$url" 2>/dev/null || xdg-open "$url" 2>/dev/null || true
wait "$forward"
