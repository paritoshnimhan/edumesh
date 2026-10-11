# EduMesh AWS deployment

EduMesh runs as four Docker containers on one AWS EC2 `t3.small` server using
K3s: Gateway, ML, DBMS, and Cloud. AWS Lambda handles transcription only.

The intentionally small Kubernetes configuration is
[`k8s/app.yaml`](k8s/app.yaml). K3s restarts a failed subject container, while
the gateway continues trying the remaining subject services.

API keys are encrypted in AWS Systems Manager Parameter Store. The EC2 and
Lambda roles can read only the two `/edumesh/*` parameters. Keys are never
stored in an image, Kubernetes manifest, or user-data script.

Live AWS resources are `edumesh-k3s` (EC2), `edumesh` (ECR), and
`edumesh-transcribe` (Lambda) in `ap-south-1`.

The public endpoint currently uses HTTP. Text questions work; browser
microphone recording needs HTTPS and a domain before it can work outside
localhost.
