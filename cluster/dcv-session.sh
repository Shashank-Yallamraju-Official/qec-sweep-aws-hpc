#!/usr/bin/env bash
# Opens the login node's DCV desktop in the browser through Session Manager, never the
# internet: cluster.yaml holds the DCV port to the VPC, so the desktop is reached at
# https://localhost:8443 through a port forward that AWS authenticates.
# usage: dcv-session.sh [-t] [cluster]
# With -t the browser shows a padlock instead of a warning: the node makes its own key
# and a signing request for localhost, mkcert on this machine signs it with the local
# authority the browser trusts, and only the certificate goes back. The key never leaves
# the node and nothing secret passes through Session Manager, whose command history is
# kept for a month. A node already serving a certificate for localhost is left alone, so
# a desktop someone else has open survives.
# Needs the AWS CLI with the Session Manager plugin and jq, and mkcert for -t; no key pair.
set -euo pipefail
trust=''
while getopts 't' option; do
  case $option in
    t) trust=1 ;;
    *) exit 2 ;;
  esac
done
shift $((OPTIND - 1))
cluster=${1:-qec} region=${AWS_REGION:-us-east-2} port=8443
command -v jq >/dev/null || { echo "jq is not installed: brew install jq" >&2; exit 2; }
if [[ -n $trust ]] && ! command -v mkcert >/dev/null; then
  echo "mkcert is not installed: brew install mkcert && mkcert -install" >&2
  exit 2
fi
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
    [[ $state == @(Pending|InProgress|Delayed|) ]] || break
    sleep 3
  done
  [[ $state == Success ]] || { echo "the node did not finish: $state" >&2; return 1; }
  aws ssm get-command-invocation --region "$region" --command-id "$command" \
    --instance-id "$node" --query StandardOutputContent --output text
}

served_names() {
  on_node 'openssl s_client -connect localhost:8443 </dev/null 2>/dev/null | openssl x509 -noout -ext subjectAltName 2>/dev/null || true'
}

# DCV takes a certificate from /etc/dcv, owned by its user and readable by nobody else:
# any other mode and it silently falls back to the self-signed one it makes itself. The
# key waits in a private directory on the node until the signed certificate arrives, so
# a signing that fails leaves the node serving what it served before.
if [[ -n $trust ]] && ! served_names | grep -q 'DNS:localhost'; then
  on_node 'install -d -m 700 /root/dcv-trust && openssl req -new -newkey rsa:2048 -nodes \
    -keyout /root/dcv-trust/dcv.key -out /root/dcv-trust/dcv.csr \
    -subj /CN=localhost -addext subjectAltName=DNS:localhost,IP:127.0.0.1 2>/dev/null \
    && cat /root/dcv-trust/dcv.csr' > "$work/dcv.csr"
  mkcert -csr "$work/dcv.csr" -cert-file "$work/dcv.pem" >/dev/null
  on_node "$(printf 'cat > /root/dcv-trust/dcv.pem <<"PEM"\n%s\nPEM\n' "$(cat "$work/dcv.pem")")
mv /root/dcv-trust/dcv.pem /etc/dcv/dcv.pem && mv /root/dcv-trust/dcv.key /etc/dcv/dcv.key
chown dcv:dcv /etc/dcv/dcv.pem /etc/dcv/dcv.key && chmod 600 /etc/dcv/dcv.pem /etc/dcv/dcv.key
rm -rf /root/dcv-trust && systemctl restart dcvserver" > /dev/null
fi

# The forward is up before the token is minted: the token lives thirty seconds.
aws ssm start-session --region "$region" --target "$node" --document-name AWS-StartPortForwardingSession \
  --parameters "portNumber=$port,localPortNumber=$port" &
forward=$!
sleep 1
kill -0 "$forward" 2>/dev/null || { echo "the port forward did not start; is the Session Manager plugin installed and port $port free?" >&2; exit 1; }
# ParallelCluster's own connect script, the one pcluster dcv-connect runs over SSH, makes
# or reuses the user's session and prints a one-time token for it.
session='' token=''
if ! read -r _ session token < <(on_node 'runuser -u ubuntu -- /opt/parallelcluster/scripts/pcluster_dcv_connect.sh /home/ubuntu' \
  | sed -n 's/^PclusterDcvServerPort=\([0-9]*\) PclusterDcvSessionId=\([^ ]*\) PclusterDcvSessionToken=\([^ ]*\).*/\1 \2 \3/p') \
  || [[ -z $token ]]; then
  kill "$forward" 2>/dev/null || true
  echo "the node gave no session token" >&2
  exit 1
fi
url="https://localhost:$port?authToken=$token#$session"
echo "$url"
open "$url" 2>/dev/null || xdg-open "$url" 2>/dev/null || true
wait "$forward"
