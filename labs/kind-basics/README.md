# kind Kubernetes Labs

This module establishes a practical foundation for using **kind**—Kubernetes IN Docker—as a local Kubernetes learning and manifest-validation environment.

The goal is not to treat kind as a production-equivalent GPU cluster. Instead, these labs use kind to isolate and study Kubernetes control-plane behavior, workload deployment, service discovery, observability, manifest portability, and the limits of local GPU integration.

This module prepares the project for later deployment onto the DGX Spark Kubernetes environment by separating two concerns:

1. **Kubernetes correctness** — API objects, reconciliation, rollout, service discovery, probes, configuration, metrics, and failure behavior.
2. **Accelerator correctness** — NVIDIA runtime integration, device discovery, GPU resource advertisement, scheduling, and actual vLLM execution.

kind is used primarily for the first category. GPU passthrough is retained as an explicitly experimental extension.

---

## 1. Learning Objectives

After completing this module, the learner should be able to:

1. Explain what kind creates and how its nodes relate to Docker containers.
2. Create, inspect, stop, and recreate a single-node Kubernetes cluster.
3. Distinguish the Docker host, kind node container, Kubernetes node, Pod, and application container.
4. Deploy a stateless HTTP service using Deployment and Service resources.
5. Inspect Kubernetes reconciliation, rollout, readiness, and failure behavior.
6. Install Prometheus and a basic exporter in a local cluster.
7. Query Kubernetes and application metrics through Prometheus.
8. Adapt vLLM Kubernetes manifests without requiring a working GPU.
9. Validate manifests through dry-run, schema validation, scheduling observation, and controlled failure.
10. Explain why a GPU request remains Pending when no device plugin advertises GPU resources.
11. Evaluate the prerequisites and limitations of exposing a host GPU to kind.
12. Identify which parts of the local setup can be promoted to the DGX Spark environment and which must be replaced.

---

## 2. Scope

Included:

- kind installation and lifecycle
- Single-node cluster creation
- Kubernetes context validation
- Namespace, Pod, Deployment, and Service fundamentals
- Port forwarding and service access
- ConfigMap and basic workload configuration
- Readiness, liveness, rollout, and restart observation
- Prometheus deployment
- Exporter deployment
- ServiceMonitor or scrape-configuration concepts
- vLLM manifest migration and static validation
- Unschedulable GPU workload analysis
- Experimental GPU passthrough assessment
- Reproducible evidence collection

Deferred:

- Production Kubernetes installation
- Multi-node DGX Spark cluster bootstrap
- NVIDIA GPU Operator production deployment
- Real vLLM GPU inference inside kind
- Distributed inference
- Persistent model cache design
- Production ingress or gateway
- High availability control plane
- Production storage
- Kubernetes security hardening
- Autoscaling and custom controllers
- Full Grafana dashboard design
- Production SLO validation

---

## 3. Why kind Is Used

kind runs Kubernetes nodes as Docker containers.

Conceptually:

```text
Physical or Virtual Host
└── Docker Engine
    └── kind Node Container
        ├── kubelet
        ├── container runtime
        ├── Kubernetes control-plane components
        └── Pod containers
```

This creates several nested boundaries:

```text
Host process namespace
Host network namespace
Host filesystem
        |
        v
kind node container
        |
        v
Kubernetes Pod sandbox
        |
        v
Application container
```

This distinction matters when debugging:

- A port exposed by the application is not automatically exposed on the host.
- A host filesystem path is not automatically available inside the kind node.
- A device visible on the host is not automatically visible in the node container.
- A device visible in the node container is not automatically advertised as a Kubernetes extended resource.
- A Kubernetes GPU request requires more than Docker-level device visibility.

kind is therefore valuable for:

- Fast cluster creation
- Manifest validation
- Kubernetes API experimentation
- Controller and operator development
- CI-based integration tests
- CPU-only service and observability labs

kind is not automatically equivalent to:

- A bare-metal GPU worker
- A managed Kubernetes service
- A production multi-node cluster
- A topology-aware accelerator platform

---

## 4. Relationship to the AI Inference Platform

The project architecture separates Serving, Control, Observability, and Experiment planes.

```text
                         Client / Test Driver
                                  |
                                  v
+----------------------------------------------------------------+
|                 kind Kubernetes Environment                    |
|                                                                |
|  HTTP Workload       Prometheus        vLLM Manifest Skeleton  |
|       |                   |                       |             |
|       +--------- metrics / state ----------------+             |
|                                                                |
|  Kubernetes API / Scheduler / Controllers / kubelet            |
+----------------------------------------------------------------+
                                  |
                                  v
                 Optional GPU Integration Experiment
```

This module is an enabling step before GPU Kubernetes deployment.

The expected progression is:

```text
kind control-plane and manifest learning
        |
        v
CPU-only deployment and observability
        |
        v
vLLM manifest validation without execution
        |
        v
GPU integration boundary assessment
        |
        v
DGX Spark Kubernetes GPU deployment
```

---

## 5. Recommended Repository Structure

```text
ai-inference-platform/
└── labs/
    └── kind-basics/
        ├── README.md
        ├── lab0-single-node-cluster/
        │   ├── README.md
        │   ├── kind-config.yaml
        │   ├── environment.md
        │   ├── observations.md
        │   └── commands/
        │       ├── verify-prerequisites.sh
        │       ├── create-cluster.sh
        │       ├── inspect-cluster.sh
        │       └── delete-cluster.sh
        ├── lab1-http-service/
        │   ├── README.md
        │   ├── manifests/
        │   │   ├── namespace.yaml
        │   │   ├── deployment.yaml
        │   │   ├── service.yaml
        │   │   └── configmap.yaml
        │   ├── commands/
        │   │   ├── deploy.sh
        │   │   ├── verify.sh
        │   │   ├── exercise-rollout.sh
        │   │   └── cleanup.sh
        │   └── observations.md
        ├── lab2-prometheus-exporter/
        │   ├── README.md
        │   ├── manifests/
        │   │   ├── namespace.yaml
        │   │   ├── exporter-deployment.yaml
        │   │   ├── exporter-service.yaml
        │   │   └── prometheus-values.yaml
        │   ├── queries/
        │   │   └── baseline-promql.md
        │   ├── commands/
        │   │   ├── install-prometheus.sh
        │   │   ├── deploy-exporter.sh
        │   │   ├── verify-targets.sh
        │   │   └── cleanup.sh
        │   └── observations.md
        ├── lab3-vllm-manifest-migration/
        │   ├── README.md
        │   ├── manifests/
        │   │   ├── namespace.yaml
        │   │   ├── configmap.yaml
        │   │   ├── deployment-cpu-validation.yaml
        │   │   ├── deployment-gpu-intent.yaml
        │   │   └── service.yaml
        │   ├── commands/
        │   │   ├── validate.sh
        │   │   ├── apply-cpu-skeleton.sh
        │   │   ├── inspect-gpu-pending.sh
        │   │   └── cleanup.sh
        │   ├── migration-notes.md
        │   └── observations.md
        ├── lab4-gpu-passthrough-assessment/
        │   ├── README.md
        │   ├── prerequisite-matrix.md
        │   ├── experiment-plan.md
        │   ├── risk-register.md
        │   ├── commands/
        │   │   ├── inspect-host-gpu.sh
        │   │   ├── inspect-docker-gpu.sh
        │   │   ├── inspect-kind-node.sh
        │   │   └── inspect-kubernetes-gpu.sh
        │   └── observations.md
        └── shared/
            ├── scripts/
            ├── evidence/
            └── templates/
                ├── environment-template.md
                └── experiment-template.md
```

The lab names are intentionally explicit. Each lab should remain independently reviewable and reproducible.

---

# Lab 0 — Build a Single-Node kind Cluster

## Objective

Create a reproducible single-node Kubernetes cluster and establish a clear mental model of the host, Docker, kind node, Kubernetes control plane, and Pod runtime layers.

## Concepts

- kind
- Docker container runtime
- Kubernetes node
- Control plane
- kubelet
- API server
- Scheduler
- Controller manager
- etcd
- kubeconfig
- Kubernetes context
- Namespace
- Cluster lifecycle

## Tasks

1. Verify Docker access.
2. Verify `kind` and `kubectl`.
3. Record tool versions.
4. Create a named single-node cluster from configuration.
5. Confirm the active Kubernetes context.
6. Inspect node and system Pods.
7. Inspect the kind node as a Docker container.
8. Compare Docker and Kubernetes views of the node.
9. Restart or recreate the cluster.
10. Delete the cluster and prove cleanup.

## Suggested Cluster Configuration

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: ai-infra-lab
nodes:
  - role: control-plane
```

The implementation should pin a tested kind node image digest or explicit version once the environment is validated.

## Suggested Commands

```bash
docker version
kind version
kubectl version --client
kind create cluster --config kind-config.yaml
kubectl config current-context
kubectl cluster-info
kubectl get nodes -o wide
kubectl get pods -A
docker ps
kind get clusters
```

## Required Evidence

`environment.md` should include:

```text
Date:
Host OS:
Host architecture:
Kernel:
Docker version:
Docker storage driver:
kind version:
kubectl version:
kind node image:
Kubernetes server version:
Cluster name:
Kubernetes context:
```

Capture:

- Cluster creation output
- Node status
- System Pod status
- Docker container corresponding to the node
- Cluster deletion output

## Failure Exercises

At least one controlled failure should be included:

- Attempt to use an incorrect Kubernetes context.
- Stop the kind node Docker container and observe cluster behavior.
- Delete a system Pod and observe reconciliation.
- Delete and recreate the cluster using the same configuration.

Do not modify critical control-plane manifests manually unless the recovery path is understood.

## Acceptance Criteria

- A named single-node cluster can be created through a script.
- The cluster reaches `Ready`.
- All required system Pods reach a healthy state.
- The active kubeconfig context is explicitly verified.
- The kind node can be correlated with its Docker container.
- The cluster can be deleted and recreated.
- Tool and node-image versions are recorded.
- At least one reconciliation or recovery behavior is documented.

## Review Questions

1. Is the kind node a virtual machine or a container?
2. Where does the Kubernetes API server run?
3. What is the difference between the Docker host and Kubernetes node?
4. Why can `docker ps` and `kubectl get pods` show different objects?
5. What does the active kubeconfig context control?
6. What state disappears when the cluster is deleted?
7. Which host resources are implicitly shared with the kind node?

---

# Lab 1 — Deploy a Standard HTTP Service

## Objective

Deploy a CPU-only HTTP application and study the basic Kubernetes workload and networking lifecycle.

## Concepts

- Pod
- ReplicaSet
- Deployment
- Service
- ClusterIP
- Labels and selectors
- ConfigMap
- Resource requests and limits
- Readiness probe
- Liveness probe
- Rolling update
- Reconciliation
- Port forwarding
- Logs and events

## Workload Requirements

The workload should:

- Run without GPU access.
- Expose an HTTP endpoint.
- Return identifiable version and Pod information.
- Expose a health endpoint.
- Support configuration through environment variables or ConfigMap.
- Use explicit resource requests and limits.
- Use readiness and liveness probes.
- Run with at least two replicas during rollout exercises.

A minimal custom service or a small existing HTTP image may be used. Record the image digest.

## Required Manifests

### Namespace

Use a dedicated namespace such as:

```text
kind-http-lab
```

### Deployment

The Deployment should define:

- Application label
- Explicit image
- Container port
- Resource requests and limits
- ConfigMap-derived configuration
- Readiness probe
- Liveness probe
- Revision history
- Replica count

### Service

Use a `ClusterIP` Service for the primary exercise.

Host access should initially use:

```bash
kubectl port-forward
```

This keeps the networking path explicit and avoids prematurely introducing ingress or NodePort behavior.

## Tasks

1. Create the namespace.
2. Apply ConfigMap, Deployment, and Service.
3. Wait for rollout completion.
4. Inspect Pods, ReplicaSet, Deployment, and endpoints.
5. Access the service through port forwarding.
6. Resolve the Service from another Pod.
7. Scale the Deployment.
8. Change the image or version configuration.
9. Observe a rolling update.
10. Introduce a broken readiness condition.
11. Observe how Service endpoints change.
12. Roll back to a working revision.
13. Delete a Pod and observe recreation.

## Suggested Commands

```bash
kubectl apply -f manifests/
kubectl get all -n kind-http-lab
kubectl get endpoints -n kind-http-lab
kubectl rollout status deployment/http-echo -n kind-http-lab
kubectl port-forward service/http-echo 8080:80 -n kind-http-lab
kubectl logs deployment/http-echo -n kind-http-lab
kubectl describe pod <pod-name> -n kind-http-lab
kubectl get events -n kind-http-lab --sort-by=.lastTimestamp
kubectl scale deployment/http-echo --replicas=3 -n kind-http-lab
kubectl rollout history deployment/http-echo -n kind-http-lab
kubectl rollout undo deployment/http-echo -n kind-http-lab
```

## Required Observations

Record:

- Deployment-to-ReplicaSet relationship
- ReplicaSet-to-Pod relationship
- Label and selector matching
- Service endpoint population
- Readiness transition behavior
- Liveness restart behavior
- Rolling update sequence
- Pod recreation after deletion
- Resource request and limit visibility
- Events generated during failure and recovery

## Acceptance Criteria

- The service is reachable from the host through port forwarding.
- The Service is reachable from inside the cluster.
- At least two replicas can serve traffic.
- Readiness controls Service endpoint membership.
- Liveness failure causes container restart.
- A rolling update and rollback are demonstrated.
- Pod deletion is recovered through Deployment reconciliation.
- Relevant events and logs are preserved.

## Review Questions

1. Does a Deployment directly create Pods?
2. What keeps the desired replica count stable?
3. What is the difference between readiness and liveness?
4. Why can a running Pod be absent from Service endpoints?
5. How does a Service select its backends?
6. What changes during a rolling update?
7. What would happen if requests and limits were omitted?
8. Which behaviors are Kubernetes mechanisms rather than kind-specific behavior?

---

# Lab 2 — Deploy Prometheus and an Exporter

## Objective

Create the first local observability plane and verify the complete path from metric production to Prometheus query.

## Concepts

- Prometheus
- Metric endpoint
- Scrape target
- Service discovery
- Counter
- Gauge
- Histogram
- Exporter
- PromQL
- Kubernetes monitoring
- ServiceMonitor
- Helm release
- Scrape configuration

## Scope Decision

This lab should begin with a lightweight exporter and a minimal Prometheus installation.

Recommended progression:

```text
Application or sample exporter
        |
        v
Kubernetes Service
        |
        v
Prometheus scrape discovery
        |
        v
PromQL query
```

Possible exporters:

- A custom HTTP application exposing `/metrics`
- Prometheus `node-exporter`, with clear documentation of containerized limitations
- `kube-state-metrics`
- A simple synthetic exporter

For the first implementation, a simple application exporter plus `kube-state-metrics` is usually easier to interpret than treating kind's containerized node metrics as production host metrics.

## Installation Options

Either approach is acceptable:

### Option A — Helm-based Prometheus stack

Advantages:

- Closer to later platform deployment
- Includes common Kubernetes integrations
- Supports ServiceMonitor workflows

Trade-offs:

- More objects
- More CRDs
- Higher cognitive load

### Option B — Minimal Prometheus manifests

Advantages:

- Easier to inspect
- Smaller surface area
- Better for learning raw scrape configuration

Trade-offs:

- Less similar to a production monitoring stack
- More manual configuration

The chosen approach must be documented in an ADR or lab note.

## Tasks

1. Create an observability namespace.
2. Install Prometheus.
3. Deploy an exporter.
4. Expose exporter metrics through a Service.
5. Configure discovery or scraping.
6. Confirm target health.
7. Port-forward the Prometheus UI.
8. Query the exporter.
9. Query Kubernetes state if available.
10. Stop or break the exporter.
11. Observe target-down behavior.
12. Restore the exporter.
13. Preserve PromQL queries and screenshots only as secondary evidence.

## Minimum Queries

The exact query names depend on the exporter, but the lab should demonstrate:

```promql
up
```

and at least:

- One counter query
- One gauge query
- One rate query
- One Kubernetes object-state query, when `kube-state-metrics` is installed

Example patterns:

```promql
rate(http_requests_total[5m])
```

```promql
kube_deployment_status_replicas_available
```

Version-specific metric names must be confirmed against the installed exporter.

## Required Observations

Record:

- Prometheus Pod and Service status
- Exporter Pod and Service status
- Scrape target labels
- Scrape interval
- Target health
- Discovery mechanism
- Metric type
- Query result
- Behavior when exporter becomes unavailable
- Delay between state change and visible Prometheus result
- Limitations of node-level metrics inside kind

## Acceptance Criteria

- Prometheus starts reproducibly.
- At least one exporter is scraped successfully.
- The `up` metric reflects exporter availability.
- At least three useful PromQL queries are documented.
- One failure is visible through Prometheus.
- The exporter is restored without rebuilding the cluster.
- The distinction between metric producer, Service, discovery, and Prometheus storage is explained.
- Containerized kind-node telemetry limitations are documented.

## Review Questions

1. Does Prometheus push or pull metrics in this lab?
2. What object tells Prometheus where to scrape?
3. What does `up == 0` mean?
4. Why can an exporter Pod be Running while its target is Down?
5. What is the difference between application metrics and Kubernetes object-state metrics?
6. Can node-exporter inside kind be treated as equivalent to host node-exporter?
7. Which metrics will later be replaced or extended by DCGM Exporter and vLLM metrics?

---

# Lab 3 — Migrate vLLM Manifests Without Running GPU Inference

## Objective

Convert the vLLM runtime configuration into Kubernetes manifests and validate Kubernetes semantics without pretending that inference is operational.

This lab intentionally separates:

- Manifest correctness
- Scheduling intent
- Runtime prerequisites
- Actual GPU execution

## Concepts

- Deployment
- Service
- ConfigMap
- Secret
- Resource request
- Extended resource
- Node selector
- Taint and toleration
- Affinity
- Startup probe
- Readiness probe
- Persistent cache
- Unschedulable Pod
- Image architecture
- Manifest overlays
- Dry-run validation

## Manifest Variants

Two variants should be maintained.

### Variant A — CPU Validation Skeleton

This variant does not run vLLM inference.

It uses a lightweight placeholder container to validate:

- Namespace
- Deployment structure
- Environment injection
- Command and argument layout
- Service
- Probes
- Volumes
- Labels
- Rollout behavior

The placeholder should make the substitution explicit. It must not be described as vLLM.

### Variant B — GPU Intent Manifest

This variant expresses the intended vLLM workload, including:

```yaml
resources:
  limits:
    nvidia.com/gpu: 1
```

In a default CPU-only kind cluster, the expected result is normally:

```text
Pod remains Pending because no node advertises nvidia.com/gpu.
```

This is a successful scheduling experiment, not a failed lab.

## Tasks

1. Identify the bare-metal vLLM startup command.
2. Separate image, model, runtime flags, ports, cache paths, and secrets.
3. Convert configuration into Kubernetes resources.
4. Add resource requests and limits.
5. Add startup and readiness design.
6. Add a Service.
7. Add a model-cache volume placeholder.
8. Validate YAML syntax.
9. Run client-side dry-run.
10. Run server-side dry-run when supported.
11. Apply the CPU validation skeleton.
12. Verify Service and probe behavior.
13. Apply the GPU intent manifest.
14. Observe Pending scheduling.
15. Inspect scheduler events.
16. Document which prerequisites are absent.
17. Produce migration notes for DGX Spark deployment.

## Validation Layers

### Layer 1 — Static YAML

Check:

- YAML parsing
- Required fields
- Resource names
- Label consistency
- Selector immutability
- Port mapping
- Volume references

### Layer 2 — Kubernetes API

Use dry-run and server validation where available.

```bash
kubectl apply --dry-run=client -f manifests/
kubectl apply --dry-run=server -f manifests/
```

### Layer 3 — CPU Skeleton Runtime

Verify:

- Deployment rollout
- Service routing
- Probe behavior
- Config injection
- Volume mount shape
- Restart and rollout behavior

### Layer 4 — GPU Scheduling Intent

Verify:

- GPU resource appears in PodSpec
- Scheduler cannot place the Pod without advertised GPU capacity
- Events show the unsatisfied resource
- No claim is made that GPU execution was validated

## Required Migration Notes

`migration-notes.md` should map:

| Bare-metal concern | Kubernetes representation |
|---|---|
| Start command | Container command and args |
| Environment variable | ConfigMap or Secret |
| HTTP port | ContainerPort and Service |
| GPU access | Extended resource request |
| Model cache | Volume |
| Startup completion | Startup probe |
| Request readiness | Readiness probe |
| Graceful shutdown | lifecycle and termination grace period |
| Runtime logs | container logs |
| Node requirements | labels, selectors, affinity, tolerations |

## Expected Missing Prerequisites

The kind environment may lack:

- NVIDIA runtime configuration in the node container
- GPU device visibility
- NVIDIA device plugin
- GPU Operator support
- `nvidia.com/gpu` allocatable capacity
- Compatible ARM64 or x86_64 image for the target host
- Model weights and cache
- Required shared-memory configuration
- Production storage
- Real GPU telemetry

## Acceptance Criteria

- A CPU validation skeleton deploys successfully.
- The intended vLLM Deployment and Service manifests exist.
- GPU resource intent is explicitly represented.
- Static and API validation pass where applicable.
- The GPU Pod remains Pending for an understood reason.
- Scheduler events are captured.
- No GPU benchmark or inference claim is made.
- Bare-metal-to-Kubernetes configuration mapping is documented.
- DGX Spark promotion requirements are listed.

## Review Questions

1. What can be validated without running vLLM?
2. Why is a Pending GPU Pod useful evidence?
3. What component advertises `nvidia.com/gpu`?
4. Does mounting `/dev/nvidia0` alone create a Kubernetes GPU resource?
5. Which probe should tolerate long model loading?
6. Why should readiness not succeed before the model is serviceable?
7. Which vLLM settings belong in ConfigMap, Secret, or immutable image configuration?
8. What must change when moving from kind to DGX Spark?

---

# Lab 4 — GPU Passthrough Assessment

## Objective

Evaluate whether and how a host NVIDIA GPU could be made available to a kind node, without making GPU-enabled kind a dependency of the core project.

The output of this lab is primarily an engineering assessment.

A successful outcome may be:

- GPU passthrough works in a constrained environment.
- Only Docker-level GPU access works.
- GPU is visible inside the kind node but not Kubernetes.
- Device plugin integration is blocked.
- The experiment is rejected as too fragile or unrepresentative.

All are valid if supported by evidence.

## Core Principle

GPU enablement requires a chain of prerequisites:

```text
Host NVIDIA driver
        |
        v
Docker GPU container support
        |
        v
GPU visibility inside kind node container
        |
        v
Node container runtime configuration
        |
        v
NVIDIA device plugin or equivalent
        |
        v
nvidia.com/gpu advertised on Kubernetes node
        |
        v
GPU Pod scheduled
        |
        v
CUDA workload succeeds
        |
        v
vLLM workload succeeds
```

Failure at one layer prevents later layers from being assumed.

## Assessment Questions

1. Does the host expose a supported NVIDIA GPU?
2. Can a normal Docker container access the GPU?
3. Can a kind node container be created with the required device/runtime access?
4. Does the node's internal container runtime support NVIDIA workloads?
5. Can the NVIDIA device plugin run correctly?
6. Does Kubernetes advertise `nvidia.com/gpu`?
7. Can a minimal CUDA Pod execute?
8. Is the setup reproducible after cluster recreation?
9. Does the approach depend on unsupported patches?
10. Does it meaningfully represent the DGX Spark target?
11. Is the maintenance cost justified?

## Experimental Gates

Proceed only after each gate passes.

### Gate 1 — Host GPU

Evidence:

```bash
nvidia-smi
```

On platforms where `nvidia-smi` is incomplete or unified-memory telemetry differs, use the target platform's validated GPU inspection path and document the limitation.

### Gate 2 — Docker GPU Access

A minimal CUDA container should detect the accelerator.

The exact image must match:

- Host architecture
- Driver compatibility
- Target CUDA requirements

Record image digest.

### Gate 3 — kind Node Visibility

Inspect whether devices and required libraries are visible from the kind node container.

Do not assume host Docker runtime settings automatically propagate into kind's internal runtime.

### Gate 4 — Kubernetes GPU Advertisement

Verify:

```bash
kubectl describe node
kubectl get node -o json
```

Expected signal:

```text
Capacity:
  nvidia.com/gpu: ...
Allocatable:
  nvidia.com/gpu: ...
```

Without this, a Pod requesting `nvidia.com/gpu` should not schedule.

### Gate 5 — CUDA Pod

Run a minimal smoke test before attempting vLLM.

### Gate 6 — vLLM

Only after the CUDA Pod succeeds should vLLM be considered.

vLLM execution is optional and does not determine completion of this lab.

## Required Risk Register

Document at least:

| Risk | Impact | Evidence | Mitigation or decision |
|---|---|---|---|
| Nested runtime complexity | High | | |
| Host-specific device mounts | High | | |
| Cluster recreation breaks setup | High | | |
| Device plugin incompatibility | High | | |
| Architecture mismatch | High | | |
| False equivalence to DGX Spark | High | | |
| Unsupported upgrade path | Medium/High | | |
| CI portability | Medium | | |

## Stop Conditions

Stop the experiment when:

- Host Docker GPU access does not work.
- Required device exposure would weaken host security unacceptably.
- The node image requires extensive unsupported mutation.
- Results cannot be reproduced after cluster recreation.
- The setup conflicts with the DGX Spark architecture.
- Time spent exceeds the learning value.
- A direct Kubernetes worker deployment is clearly more representative.

Stopping should be documented as an engineering decision, not treated as failure.

## Required Deliverables

### `prerequisite-matrix.md`

Track:

```text
Host driver:
Host architecture:
Docker GPU runtime:
kind version:
kind node image:
Kubernetes version:
Node internal runtime:
NVIDIA device plugin version:
CUDA test image:
Observed GPU capacity:
Observed allocatable GPU:
```

### `experiment-plan.md`

For every attempt, record:

- Hypothesis
- Change made
- Expected result
- Actual result
- Logs and events
- Reproduction command
- Rollback
- Decision

### `risk-register.md`

Document long-term suitability.

### `observations.md`

Conclude with one of:

```text
Supported for local experiments
Partially supported
Unsupported in current environment
Technically possible but not recommended
Deferred in favor of DGX Spark worker integration
```

## Acceptance Criteria

- The prerequisite chain is explicitly evaluated.
- Docker-level GPU access is distinguished from Kubernetes-level GPU scheduling.
- Device visibility is distinguished from resource advertisement.
- A minimal CUDA workload is used before any vLLM attempt.
- Failures are preserved with logs and events.
- Reproducibility after cluster recreation is tested if passthrough succeeds.
- The result is not described as production-equivalent.
- A clear go/no-go recommendation is produced.
- The core kind learning path remains functional without GPU passthrough.

## Review Questions

1. Why is Docker GPU access insufficient to prove Kubernetes GPU support?
2. What does the NVIDIA device plugin contribute?
3. Why must `Capacity` and `Allocatable` be checked?
4. What runtime executes Pod containers inside a kind node?
5. Why can nested container runtimes complicate accelerator support?
6. What evidence is required before running vLLM?
7. Would direct DGX Spark worker integration provide a more representative result?
8. Is local GPU-enabled kind valuable for this project's future CI?

---

## 6. Evidence Standard

Every lab should preserve:

1. **Environment** — versions, architecture, images, configuration.
2. **Commands** — exact commands or scripts.
3. **Raw evidence** — logs, events, YAML output, metrics, and error messages.
4. **Observation** — what happened.
5. **Interpretation** — why it happened.
6. **Limitation** — what the experiment does not prove.
7. **Next action** — what should be tested next.

A screenshot may supplement evidence but should not replace:

- Source manifests
- Command output
- Events
- Logs
- Machine-readable data

---

## 7. Codex Implementation Guidance

Codex should implement each lab independently.

For each lab, generate:

1. Lab-specific `README.md`
2. Version-aware prerequisites
3. Shell scripts using strict mode
4. Kubernetes manifests
5. Verification commands
6. Cleanup commands
7. Expected behavior
8. Expected failure behavior
9. Acceptance checklist
10. Human-review questions

Shell scripts should generally use:

```bash
set -euo pipefail
```

Scripts should:

- Avoid hidden global state.
- Verify the active Kubernetes context.
- Use a dedicated namespace.
- Print major actions.
- Fail with actionable errors.
- Be safe to rerun where practical.
- Preserve evidence before cleanup.
- Avoid deleting unrelated clusters or namespaces.

Manifests should:

- Use explicit namespaces.
- Use consistent labels.
- Define resource requests and limits.
- Pin image versions or digests after validation.
- Include probes where meaningful.
- Avoid privileged mode unless the GPU experiment explicitly requires and justifies it.
- Distinguish placeholder workloads from real vLLM workloads.
- Include comments only where they explain a non-obvious decision.

Codex must not:

- Invent successful GPU results.
- Describe a placeholder as vLLM.
- Suppress Pending or failure evidence.
- Install GPU Operator blindly into kind.
- Treat kind node metrics as production bare-metal metrics.
- Assume x86_64 images work on ARM64.
- Modify the host permanently without a rollback plan.

---

## 8. Module Deliverables

The completed module should contain:

- Reproducible single-node kind cluster scripts
- Cluster environment record
- CPU HTTP Deployment and Service
- Probe, rollout, and reconciliation exercises
- Prometheus installation
- At least one working exporter
- Saved PromQL queries
- vLLM Kubernetes manifest skeleton
- GPU-intent manifest and Pending analysis
- Bare-metal-to-Kubernetes migration notes
- GPU passthrough prerequisite matrix
- GPU passthrough risk assessment
- Final recommendation for DGX Spark promotion

---

## 9. Completion Checklist

### Lab 0 — Cluster

- [ ] Docker access verified
- [ ] kind and kubectl versions recorded
- [ ] Single-node cluster created
- [ ] Node reaches Ready
- [ ] System Pods inspected
- [ ] kind node correlated with Docker container
- [ ] Context verified
- [ ] Cluster deleted and recreated
- [ ] One reconciliation or recovery behavior documented

### Lab 1 — HTTP Service

- [ ] Namespace created
- [ ] ConfigMap applied
- [ ] Deployment rolled out
- [ ] Service endpoints populated
- [ ] Host access verified through port forwarding
- [ ] In-cluster access verified
- [ ] Scaling tested
- [ ] Readiness failure tested
- [ ] Liveness restart tested
- [ ] Rolling update tested
- [ ] Rollback tested
- [ ] Pod recreation observed

### Lab 2 — Prometheus

- [ ] Prometheus installed
- [ ] Exporter installed
- [ ] Target discovered
- [ ] `up` verified
- [ ] Counter query executed
- [ ] Gauge query executed
- [ ] Rate query executed
- [ ] Target failure observed
- [ ] Target recovery observed
- [ ] kind telemetry limitations documented

### Lab 3 — vLLM Manifests

- [ ] Bare-metal command decomposed
- [ ] CPU validation skeleton created
- [ ] CPU skeleton deployed
- [ ] vLLM Service manifest created
- [ ] GPU resource request represented
- [ ] Client dry-run passed
- [ ] Server dry-run attempted
- [ ] GPU Pod Pending state inspected
- [ ] Scheduler event preserved
- [ ] Missing prerequisites documented
- [ ] DGX Spark migration notes completed

### Lab 4 — GPU Assessment

- [ ] Host GPU assessed
- [ ] Docker GPU access assessed
- [ ] kind node visibility assessed
- [ ] Internal runtime assessed
- [ ] Device plugin requirement assessed
- [ ] Kubernetes GPU capacity checked
- [ ] CUDA Pod attempted only after prerequisites
- [ ] Reproducibility evaluated
- [ ] Risks documented
- [ ] Go/no-go recommendation produced

---

## 10. Final Review Questions

At the end of the module, the learner should answer:

1. What does kind run inside Docker?
2. Where do Kubernetes control-plane components run?
3. What is the difference between a kind node and a Pod?
4. How does a Deployment maintain desired state?
5. How does readiness affect Service traffic?
6. How does Prometheus discover and scrape a target?
7. Which metrics in kind are representative of Kubernetes behavior but not bare-metal capacity?
8. Which parts of a vLLM deployment can be validated without a GPU?
9. Why does a GPU-requesting Pod remain Pending in a default kind cluster?
10. What is the difference between GPU device visibility and `nvidia.com/gpu` advertisement?
11. Which components are required between the host driver and a scheduled CUDA Pod?
12. Which manifests can be promoted to DGX Spark unchanged?
13. Which manifests require architecture-, runtime-, or GPU-specific overlays?
14. Is GPU-enabled kind justified for this project?

---

## 11. Exit Criteria

This module is complete when:

- The kind cluster can be recreated from version-controlled configuration.
- A CPU HTTP workload demonstrates deployment, service discovery, probes, scaling, rollout, rollback, and reconciliation.
- Prometheus scrapes at least one exporter and exposes useful queries.
- vLLM Kubernetes manifests are structurally validated without falsely claiming GPU execution.
- The unschedulable GPU path is understood through Kubernetes events.
- GPU passthrough is assessed through a layered prerequisite model.
- A documented decision determines whether local GPU-enabled kind should continue.
- The project is ready to promote validated Kubernetes resources into the DGX Spark cluster.

The expected result is not:

> kind successfully ran vLLM on a GPU.

The expected result is:

> Kubernetes behavior, observability, and vLLM deployment intent were validated locally; accelerator-specific requirements and limitations were isolated; and the transition path to DGX Spark GPU workers was documented with evidence.
