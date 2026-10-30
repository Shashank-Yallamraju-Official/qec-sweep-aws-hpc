# The MPI queue's nodes carry an EFA-only interface beside the primary one, and
# EC2 gives no public IP to an instance with two, so they live in a private
# subnet that reaches the internet through a NAT gateway. The gateway bills by
# the hour and exists only while the cluster does; the subnet, its route table
# and the S3 endpoint cost nothing and stay.

data "aws_subnet" "public" {
  id = var.public_subnet_id
}

resource "aws_subnet" "mpi" {
  vpc_id            = data.aws_subnet.public.vpc_id
  availability_zone = data.aws_subnet.public.availability_zone
  cidr_block        = var.mpi_subnet_cidr
  tags              = { Name = "qec-sweep-mpi" }
}

resource "aws_route_table" "mpi" {
  vpc_id = data.aws_subnet.public.vpc_id
  tags   = { Name = "qec-sweep-mpi" }
}

resource "aws_route_table_association" "mpi" {
  subnet_id      = aws_subnet.mpi.id
  route_table_id = aws_route_table.mpi.id
}

# Results and the configure script's downloads bypass the gateway's per-byte charge.
resource "aws_vpc_endpoint" "s3" {
  vpc_id          = data.aws_subnet.public.vpc_id
  service_name    = "com.amazonaws.${var.region}.s3"
  route_table_ids = [aws_route_table.mpi.id]
}

resource "aws_eip" "nat" {
  count  = var.nat_gateway ? 1 : 0
  domain = "vpc"
}

resource "aws_nat_gateway" "mpi" {
  count         = var.nat_gateway ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = data.aws_subnet.public.id
  tags          = { Name = "qec-sweep-mpi" }
}

resource "aws_route" "mpi_internet" {
  count                  = var.nat_gateway ? 1 : 0
  route_table_id         = aws_route_table.mpi.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.mpi[0].id
}
