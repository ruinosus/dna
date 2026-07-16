# DNA-emitted Foundry hosted-agent container: memory-agent (hosting.mode=hosted, target=foundry).
#
# Built remotely by ACR (docker.remoteBuild in azure.yaml). Serves the Responses
# protocol on 8088 via ResponsesHostServer (started by main.py), invoked through
# the Foundry gateway. Foundry hosted agents run on linux/amd64 — build for that
# platform (`docker build --platform linux/amd64 ...` if you build locally).
FROM python:3.12-slim

WORKDIR /app

COPY . user_agent/
WORKDIR /app/user_agent

RUN if [ -f requirements.txt ]; then \
        pip install --no-cache-dir -r requirements.txt; \
    else \
        echo "No requirements.txt found"; \
    fi

EXPOSE 8088

CMD ["python", "main.py"]
