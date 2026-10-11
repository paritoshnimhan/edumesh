# EduMesh teacher demo script

This is a simple three-person presentation. It takes about 6 to 8 minutes.

## Before the demo

1. Open [http://65.0.66.42](http://65.0.66.42) using **HTTP**.
2. Keep the AWS Console or terminal ready only if the teacher asks for proof.
3. Prepare these example questions:
   - `Explain supervised learning in machine learning.`
   - `What is database normalization?`
   - `Explain Kubernetes pods and services.`

## Person 1 — Project introduction and website (about 2 minutes)

Say:

> Good morning. Our project is EduMesh. It is a learning assistant for three
> subjects: Machine Learning, DBMS, and Cloud Computing. A student can type one
> question, and the system finds which subject service understands it best.

Show the website and type the ML example question.

Say:

> We do not send every question directly to one fixed service. First, all three
> services check the question. The system chooses the service with the best
> score. Here, ML wins because the question is about supervised learning.

Show the generated answer.

Then say:

> The same website can answer DBMS and Cloud questions. This makes the project
> a small distributed system, not just one single program.

## Person 2 — Docker and Kubernetes (about 2 to 3 minutes)

Say:

> We divided the application into four Docker containers: Gateway, ML, DBMS,
> and Cloud. Docker makes the application run in the same way on our laptop and
> on AWS.

Show `docker-compose.yml` or the diagram in `README.md`.

Say:

> Kubernetes runs these containers on AWS. The Gateway receives the student
> question. ML, DBMS, and Cloud are separate services. Kubernetes monitors the
> containers and restarts a subject service if it stops.

Say:

> We tested this by deleting the ML Kubernetes pod. Kubernetes automatically
> created a new healthy ML pod in around 12 seconds. So one failed subject
> container does not stop the complete project.

Show `k8s/app.yaml` and point out that it is kept in one file to make the
deployment easy to understand.

## Person 3 — AWS and serverless part (about 2 minutes)

Say:

> Our application is hosted on AWS. We use EC2 to run K3s Kubernetes. Amazon
> ECR stores our Docker image. AWS Parameter Store keeps API keys encrypted, so
> keys are not written in the source code or Docker image.

Say:

> We also use AWS Lambda for audio transcription. Lambda is serverless, which
> means AWS runs it only when audio transcription is requested. We do not need
> to keep a separate transcription server running all the time.

Say:

> Therefore, our design is hybrid: Kubernetes and Docker run the main
> distributed application, while Lambda handles the short audio task.

End with:

> In summary, EduMesh shows service routing, Docker containers, Kubernetes
> self-healing, AWS hosting, secure key storage, and serverless Lambda in one
> simple student project.

## If the teacher asks questions

**Why not use only Lambda?**

> Kubernetes and Docker were required for this project. Lambda is used where it
> makes the most sense: short transcription requests.

**What happens if ML stops?**

> Kubernetes restarts ML automatically. Until it is ready, the Gateway can
> still ask DBMS and Cloud.

**Why use Parameter Store?**

> It stores API keys securely in AWS instead of exposing them in source code.

**Why is the public link HTTP?**

> The demonstration deployment currently uses HTTP. HTTPS and a domain can be
> added later for public microphone support.
