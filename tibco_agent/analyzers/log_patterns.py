from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class LogPattern:
    id: str
    regex: re.Pattern
    product: str        # "bw" | "flogo" | "k8s" | "any"
    title: str
    root_causes: list[str]
    fixes: list[str]
    severity: str = "ERROR"
    tags: list[str] = field(default_factory=list)


def _p(
    id: str, pattern: str, product: str, title: str,
    root_causes: list[str], fixes: list[str],
    severity: str = "ERROR", tags: list[str] | None = None,
) -> LogPattern:
    return LogPattern(
        id=id, regex=re.compile(pattern, re.IGNORECASE), product=product,
        title=title, root_causes=root_causes, fixes=fixes,
        severity=severity, tags=tags or [],
    )


DEFAULT_PATTERNS: list[LogPattern] = [

    _p("K8S-001", r"CrashLoopBackOff", "k8s", "Pod CrashLoopBackOff",
       root_causes=[
           "Missing required environment variable ($env[VAR] not set in deployment)",
           "Port conflict on trigger or admin port",
           "Out of memory during startup",
           "Invalid .flogo descriptor or BW application archive",
       ],
       fixes=[
           "kubectl logs <pod> --previous  — see the crash output",
           "kubectl describe pod <pod>  — check Events section",
           "Verify all required env vars are set in deployment/secret",
           "Ensure memory limits are sufficient for startup overhead",
       ],
       tags=["kubernetes", "startup"]),

    _p("K8S-002", r"OOMKilled", "k8s", "Container Killed — Out of Memory",
       root_causes=[
           "Container exceeded its memory limit",
           "Memory leak — flows holding large payloads in flow variables",
           "Large array processing without chunking",
           "JVM heap not tuned (for BW containers)",
       ],
       fixes=[
           "Increase memory limit in the K8s deployment spec",
           "kubectl top pods  — profile live memory usage",
           "For BW: increase BW_JVM_MAX_HEAP (e.g., -Xmx1024m)",
           "Check for flows storing full HTTP response bodies in variables after use",
       ],
       tags=["kubernetes", "memory", "performance"]),

    _p("K8S-003", r"ImagePullBackOff|ErrImagePull", "k8s", "Image Pull Failure",
       root_causes=[
           "Wrong image name or tag in the deployment spec",
           "Container registry unreachable from the cluster",
           "Missing or expired imagePullSecret",
       ],
       fixes=[
           "kubectl describe pod <pod>  — see exact image name being pulled",
           "Verify registry credentials: kubectl get secret",
           "Use imagePullPolicy: Always with a unique tag (avoid 'latest')",
       ],
       tags=["kubernetes", "deployment"]),

    _p("K8S-004", r"Readiness probe failed|readiness probe", "k8s", "Readiness Probe Failing",
       root_causes=[
           "Probe points to wrong port or path",
           "Application not fully initialized when probe fires",
           "Application crashed but liveness hasn't caught it",
       ],
       fixes=[
           "Flogo: readiness probe → /ping on admin port 9999",
           "BWCE: readiness probe → /healthcheck on the admin port",
           "Increase initialDelaySeconds to allow full startup",
           "kubectl exec -it <pod> -- curl localhost:<port>/ping  — verify probe path",
       ],
       tags=["kubernetes", "health"]),

    _p("NET-001", r"dial tcp .+: connect: connection refused", "any", "Connection Refused",
       root_causes=[
           "Target service is down or not yet ready",
           "Wrong host or port in connector configuration",
           "NetworkPolicy blocking egress from the pod",
       ],
       fixes=[
           "kubectl get svc && kubectl get endpoints  — verify target exists",
           "kubectl exec -it <pod> -- nslookup <service-name>  — DNS check",
           "kubectl exec -it <pod> -- nc -zv <host> <port>  — port reachability",
           "Review NetworkPolicy resources if egress is restricted",
       ],
       tags=["networking", "connectivity"]),

    _p("NET-002", r"context deadline exceeded|request timeout|timed out", "any", "Timeout",
       root_causes=[
           "Downstream service is slow or overloaded",
           "Timeout value on the activity is too low for the operation",
           "Network latency spike or packet loss",
       ],
       fixes=[
           "Identify which call timed out from the stack trace above the error",
           "Check downstream service health and response times",
           "Increase timeout on the REST/HTTP activity if the operation is legitimately slow",
           "Add retry with exponential backoff for transient timeouts",
       ],
       tags=["networking", "performance", "timeout"]),

    _p("MEM-001", r"OutOfMemoryError.*Java heap space|java\.lang\.OutOfMemoryError", "bw",
       "JVM Heap Out of Memory",
       root_causes=[
           "JVM heap too small for the workload",
           "Processing very large XML or JSON in memory",
           "Memory leak — BW process instances not completing",
           "Data accumulation in shared variables",
       ],
       fixes=[
           "Increase BW_JVM_MAX_HEAP (e.g., BW_JVM_MAX_HEAP=-Xmx1024m)",
           "kubectl top pods  — confirm memory trend before and after fix",
           "Check for BW processes stuck in Waiting state in TIBCO Administrator",
           "Use streaming XML parsing for documents > 1MB",
           "Review loops that accumulate data into arrays or string concatenation",
       ],
       tags=["bw", "memory", "jvm"]),

    _p("MEM-002", r"GC overhead limit exceeded", "bw", "GC Overhead Limit Exceeded",
       root_causes=[
           "JVM spending > 98% of time in garbage collection",
           "Heap too small relative to working object set",
           "Large number of short-lived objects from XML or JSON parsing",
       ],
       fixes=[
           "Significantly increase BW_JVM_MAX_HEAP",
           "Add -XX:+UseG1GC to JVM args for better large-heap GC",
           "Profile heap: attach JVM diagnostic tools or use -verbose:gc flag",
       ],
       tags=["bw", "memory", "jvm", "gc"]),

    _p("BW-001", r"TIBCO-BW-JDBC-\d+.*[Cc]onnection|Failed to obtain.*JDBC|JDBC.*pool", "bw",
       "JDBC Connection Failure",
       root_causes=[
           "Database unreachable (wrong host/port, network policy, DB down)",
           "Connection pool exhausted — all connections in active use",
           "Stale connections — no validation query configured",
           "Max pool wait timeout exceeded",
       ],
       fixes=[
           "kubectl exec -it <pod> -- nc -zv <db-host> <port>  — verify connectivity",
           "Increase maxPoolSize in the JDBC shared resource configuration",
           "Add validationQuery=SELECT 1 and set validationInterval=30000",
           "Check for long-running transactions holding connections open",
       ],
       tags=["bw", "jdbc", "database"]),

    _p("BW-002", r"TIBCO-BW-EMS-\d+.*[Cc]onnection|EMS.*[Cc]onnection.*[Ll]ost", "bw",
       "EMS Connection Lost",
       root_causes=[
           "EMS server is down or restarting",
           "Network interruption between pod and EMS",
           "EMS session timeout with no heartbeat configured",
       ],
       fixes=[
           "Set reconnAttemptCount=10 and reconnAttemptDelay=5000 on EMS connection resource",
           "Verify EMS server is running and accessible from the pod",
           "Check firewall/security group allows traffic from pod CIDR to EMS port",
       ],
       tags=["bw", "ems", "messaging"]),

    _p("BW-003", r"TIBCO-BW-PALETTE-FILE-\d+|Error reading file", "bw", "File Palette Error",
       root_causes=[
           "File path does not exist in the container filesystem",
           "Container user lacks read permission on the file",
           "Volume not mounted or mounted at the wrong path",
       ],
       fixes=[
           "Verify the path is correct relative to the container root",
           "Check volume mount in the deployment spec",
           "Container often runs as non-root — ensure file is readable by that UID",
       ],
       tags=["bw", "file", "permissions"]),

    _p("BW-004", r"%%\w+%%|substitution.*not found|AppProperty.*not found", "bw",
       "Missing Substitution Variable",
       root_causes=[
           "BW application uses %%VAR%% that was not replaced at startup",
           "BW_APP_SUBSTITUTION_VARIABLES or ConfigMap missing a required key",
       ],
       fixes=[
           "List all substitution variables in the application .properties file",
           "Ensure ConfigMap/Secret contains all required keys",
           "Check BW_APP_SUBSTITUTION_VARIABLES environment variable in the deployment",
       ],
       tags=["bw", "configuration", "startup"]),

    _p("NULL-001", r"NullPointerException", "any", "NullPointerException",
       root_causes=[
           "Mapper or XPath expression references a field that is null or absent in the payload",
           "Upstream API response missing an expected field (schema drift)",
           "Optional field used without an existence guard",
       ],
       fixes=[
           "Flogo: wrap optional fields — coalesce($activity.output.field, 'default')",
           "BW XPath: add exists() guard — if (exists($in/field)) then $in/field else 'default'",
           "Add schema validation at the service boundary to catch upstream contract changes early",
       ],
       tags=["null", "mapper", "xslt"]),

    _p("POOL-001", r"connection pool.*exhausted|no connection.*available|pool.*full|wait.*pool", "any",
       "Connection Pool Exhausted",
       root_causes=[
           "All connections in pool are in active use",
           "Long-running transactions holding connections",
           "Pool size too small for current concurrency level",
       ],
       fixes=[
           "Increase maxPoolSize on the JDBC or HTTP connector resource",
           "Set a connection timeout so requests fail fast instead of queuing indefinitely",
           "Identify slow queries or transactions holding connections too long",
           "Ensure (replicas × threads) does not exceed pool capacity",
       ],
       tags=["pool", "performance", "jdbc"]),

    _p("FLOGO-RT-001", r"trigger.*failed to start|activity.*panic|runtime.*panic|goroutine.*panic", "flogo",
       "Flogo Runtime Panic",
       root_causes=[
           "Nil pointer dereference in activity or mapper code",
           "Type assertion failure in Go runtime",
           "Invalid activity configuration passed at trigger startup",
       ],
       fixes=[
           "Check the full goroutine stack trace above this line",
           "Review any custom activities for missing nil checks",
           "Verify mapper output types exactly match the activity input schema",
           "Run with a minimal test payload to isolate which activity panics",
       ],
       tags=["flogo", "panic", "runtime"]),
]
