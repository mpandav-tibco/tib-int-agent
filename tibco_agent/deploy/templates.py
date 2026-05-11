"""Generate deployment artifacts — docker-compose.yml and Kubernetes manifests."""
from __future__ import annotations

import base64
import re
import textwrap

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-")[:40]


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def render_docker_compose(agent, image: str = "tibco-ai-agent-chainlit:latest") -> str:
    slug = _slugify(agent.name)
    return textwrap.dedent(f"""\
        # AgentForge — Docker Compose deployment for agent: {agent.name}
        # Run with: docker compose up -d
        version: "3.9"
        services:
          {slug}:
            image: {image}
            container_name: agent-{slug}-{agent.id[:8]}
            restart: unless-stopped
            ports:
              - "8080:8080"
            environment:
              AGENT_ID: "{agent.id}"
              LLM_PROVIDER: "{agent.llm_provider}"
              LLM_MODEL: "{agent.llm_model}"
              LLM_API_KEY: "{agent.llm_api_key}"
              LLM_API_BASE: "{agent.llm_api_base}"
              EMBED_MODEL: "{agent.embed_model}"
              VECTOR_DB: "{agent.vector_db}"
              VECTOR_DB_URL: "{agent.vector_db_url}"
              VECTOR_DB_API_KEY: "{agent.vector_db_api_key}"
              COLLECTION_NAME: "{agent.collection_name}"
              CHAINLIT_AUTH_SECRET: "change-me-before-going-to-production"
    """)


def render_k8s_manifests(agent) -> dict[str, str]:
    slug = _slugify(agent.name)
    short_id = agent.id[:8]
    name = f"agent-{slug}-{short_id}"

    secret_data = {
        "LLM_API_KEY":       _b64(agent.llm_api_key),
        "VECTOR_DB_API_KEY": _b64(agent.vector_db_api_key),
        "CHAINLIT_AUTH_SECRET": _b64("change-me-before-going-to-production"),
    }

    configmap_data = {
        "AGENT_ID":       agent.id,
        "LLM_PROVIDER":   agent.llm_provider,
        "LLM_MODEL":      agent.llm_model,
        "LLM_API_BASE":   agent.llm_api_base,
        "EMBED_MODEL":    agent.embed_model,
        "VECTOR_DB":      agent.vector_db,
        "VECTOR_DB_URL":  agent.vector_db_url,
        "COLLECTION_NAME": agent.collection_name,
    }

    secret_yaml = textwrap.dedent(f"""\
        apiVersion: v1
        kind: Secret
        metadata:
          name: {name}-secret
        type: Opaque
        data:
    """) + "".join(f"  {k}: {v}\n" for k, v in secret_data.items())

    configmap_yaml = textwrap.dedent(f"""\
        apiVersion: v1
        kind: ConfigMap
        metadata:
          name: {name}-config
        data:
    """) + "".join(f"  {k}: \"{v}\"\n" for k, v in configmap_data.items())

    deployment_yaml = textwrap.dedent(f"""\
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: {name}
          labels:
            app: {name}
        spec:
          replicas: 1
          selector:
            matchLabels:
              app: {name}
          template:
            metadata:
              labels:
                app: {name}
            spec:
              containers:
                - name: chainlit
                  image: tibco-ai-agent-chainlit:latest
                  imagePullPolicy: IfNotPresent
                  ports:
                    - containerPort: 8080
                  envFrom:
                    - configMapRef:
                        name: {name}-config
                    - secretRef:
                        name: {name}-secret
                  resources:
                    requests:
                      cpu: "250m"
                      memory: "512Mi"
                    limits:
                      cpu: "1"
                      memory: "2Gi"
    """)

    service_yaml = textwrap.dedent(f"""\
        apiVersion: v1
        kind: Service
        metadata:
          name: {name}
        spec:
          selector:
            app: {name}
          ports:
            - protocol: TCP
              port: 80
              targetPort: 8080
    """)

    ingress_yaml = textwrap.dedent(f"""\
        # Replace <your-domain> with your actual ingress hostname
        apiVersion: networking.k8s.io/v1
        kind: Ingress
        metadata:
          name: {name}
          annotations:
            nginx.ingress.kubernetes.io/rewrite-target: /
        spec:
          rules:
            - host: {slug}.agents.<your-domain>
              http:
                paths:
                  - path: /
                    pathType: Prefix
                    backend:
                      service:
                        name: {name}
                        port:
                          number: 80
    """)

    kustomization_yaml = textwrap.dedent("""\
        apiVersion: kustomize.config.k8s.io/v1beta1
        kind: Kustomization
        resources:
          - secret.yaml
          - configmap.yaml
          - deployment.yaml
          - service.yaml
          - ingress.yaml
    """)

    readme = textwrap.dedent(f"""\
        # Agent: {agent.name}
        # Generated by AgentForge

        ## Prerequisites
        - kubectl configured to point at your cluster
        - The chainlit image available in your cluster's registry:
            docker build -t tibco-ai-agent-chainlit:latest -f Dockerfile .
            # Push to your registry if needed

        ## Deploy
            kubectl create namespace agents   # once
            kubectl -n agents apply -k .

        ## Update ingress host
        Edit ingress.yaml and replace:
            {slug}.agents.<your-domain>
        with your actual hostname or IP.

        ## Remove
            kubectl -n agents delete -k .
    """)

    return {
        "secret.yaml":         secret_yaml,
        "configmap.yaml":      configmap_yaml,
        "deployment.yaml":     deployment_yaml,
        "service.yaml":        service_yaml,
        "ingress.yaml":        ingress_yaml,
        "kustomization.yaml":  kustomization_yaml,
        "README.txt":          readme,
    }
