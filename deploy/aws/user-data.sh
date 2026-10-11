#!/bin/bash
set -euo pipefail

# IMAGE_URI and ECR_REGISTRY are replaced by the deployment command. No API keys
# belong in this file: application containers retrieve them from Parameter Store.
dnf install -y awscli curl
systemctl enable --now amazon-ssm-agent
curl --fail --location --retry 3 https://get.k3s.io -o /root/install-k3s.sh
INSTALL_K3S_CHANNEL=stable sh /root/install-k3s.sh --secrets-encryption

mkdir -p /opt/edumesh
echo 'APP_MANIFEST_BASE64' | base64 --decode > /opt/edumesh/app.yaml
until /usr/local/bin/k3s kubectl get nodes >/dev/null 2>&1; do sleep 5; done
/usr/local/bin/k3s kubectl create namespace edumesh --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f -
ECR_PASSWORD=$(aws ecr get-login-password --region ap-south-1)
/usr/local/bin/k3s kubectl -n edumesh create secret docker-registry ecr-regcred \
  --docker-server=ECR_REGISTRY --docker-username=AWS --docker-password="$ECR_PASSWORD" \
  --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f -
sed 's|IMAGE_URI|IMAGE_URI_VALUE|g' /opt/edumesh/app.yaml | /usr/local/bin/k3s kubectl apply -f -
