# Docker Standards

Docker artifacts begin in Phase 1 after official base-image and dependency verification.

Every service image must:

- use an official, verified, explicitly pinned base image;
- use a multi-stage build; an exception requires a documented technical reason and equivalent runtime-minimization evidence;
- install only the service's declared production dependencies;
- run as a non-root user unless a documented requirement prevents it;
- copy dependency metadata before application source to support reproducible caching;
- avoid package-manager caches, compilers, and test tooling in the runtime stage;
- contain no real secrets or environment-specific configuration;
- expose one primary application process per container where appropriate;
- handle termination signals and graceful shutdown;
- write logs to standard output/error in structured form;
- avoid durable writes to container-local paths;
- include OCI metadata identifying source revision and service version;
- build reproducibly under CI using the committed lockfile.

Infrastructure images must use official publishers and pinned stable tags or digests. Floating `latest` tags are forbidden.

Health behavior is implemented by the workload and mapped to orchestration probes. Image-level health checks must not introduce conflicting semantics.

Build contexts must exclude secrets, local virtual environments, caches, test artifacts, and infrastructure data volumes.
