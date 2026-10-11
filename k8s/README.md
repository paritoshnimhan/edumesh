# EduMesh Kubernetes deployment

This is the intentionally simple Kubernetes setup. `app.yaml` contains every
resource and runs the four existing Docker containers on one AWS EC2 machine
using K3s.

K3s restarts a stopped ML, DBMS, or Cloud container automatically. The gateway
continues trying the other subject services if one is unavailable.

Before deployment, replace `IMAGE_URI` in `app.yaml` with the ECR image URI.
The deployment command creates only `ecr-regcred` on the EC2 machine. API keys
remain encrypted in AWS Parameter Store and are read through the EC2 role.

```bash
kubectl apply -f app.yaml
kubectl get pods -n edumesh
```
