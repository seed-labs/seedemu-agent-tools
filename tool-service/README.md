# SEEDemu Agent Tool Service


FastAPI service exposing agent-facing operations for SEED-Emulator.

## Development Setup

From this directory, create and activate a virtual environment:

```bash
python -m venv .venv
```

On Linux or macOS:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the service and development dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run the Service

```bash
python -m uvicorn seedemu_tool_service.main:app --reload
```

Benchmark topology deployment resources are documented with their owning domain in
`seedemu_tool_service/tools/benchmark/README.md`; other Tool Service domains do not
depend on them.

The SEED workspace itself is **not** a tool-service setting: this service makes no assumption about where
the SEED emulator lives. `benchmark.topology.discover_python` accepts any existing trusted Python
entrypoint selected by the user, performs a bounded Python-only trial compile, parses the generated Compose,
and returns a normalized service/network/probe descriptor. `benchmark.runtime.describe` produces the equivalent
read-only descriptor input for an already running project through the Docker SDK. Clients never invoke Docker CLI;
all runtime discovery remains behind this API.
The declared `seed_root` identifies the SEED library checkout; the topology script may be elsewhere on the host.
`benchmark.topology.lifecycle` can build, start, check, and stop exactly that bound Compose artifact.
Its path must remain inside the matching artifact ID and its project name is validated.

The service is then available at:

- API: <http://127.0.0.1:8000>
- OpenAPI documentation: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/api/v1/health>
- Runtime backend: <http://127.0.0.1:8000/api/v1/runtime>
- Tool discovery: <http://127.0.0.1:8000/api/v1/tools>
- Tool invocation: <http://127.0.0.1:8000/api/v1/tools/{name}/invoke>

Invoke a tool by posting its arguments as the request body:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/tools/network.inspect_ip_address/invoke \
  -H "Content-Type: application/json" \
  -d '{"address": "10.0.0.1"}'
```

Errors use a structured envelope with a machine-readable code:

```json
{"error": {"code": "invalid_arguments", "message": "...", "detail": [...]}}
```

## Invoke a Tool

Invoke a registered tool by posting its arguments to the tool-specific endpoint:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/tools/network.inspect_ip_address/invoke \
  -H 'Content-Type: application/json' \
  -d '{"address":"2001:0db8::1"}'
```

The response identifies the invoked tool and contains its structured result:

```json
{
  "name": "network.inspect_ip_address",
  "result": {
    "address": "2001:db8::1",
    "version": 6,
    "is_private": true,
    "is_loopback": false,
    "is_multicast": false,
    "is_global": false
  },
  "duration_ms": 0.123
}
```

The request object is validated against the input schema returned by the tool-discovery endpoint.
This example does not require a running Docker daemon or SEED emulation.

Docker-backed tools use the same endpoint. For example, after starting a SEED emulation and
checking its container names with `docker ps`:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/tools/network.ping/invoke \
  -H 'Content-Type: application/json' \
  -d '{"source":"as150h-web-10.150.0.71","target":"10.151.0.71","count":2}'
```

An unreachable destination is a successful tool observation and returns HTTP `200` with
`reachable: false`. A missing source container returns HTTP `404`; a Docker backend failure
returns HTTP `502`.

## Run Tests

```bash
python -m pytest
```

## Run with Docker Compose

The container connects to the host Docker daemon through `/var/run/docker.sock`. This gives
the tool service control over host containers, images, networks, and volumes. Only run the
service from trusted code and do not expose its API to untrusted networks.

On Linux, set `DOCKER_GID` to the group owner of the Docker socket so the non-root application
user can access it:

```bash
export DOCKER_GID="$(stat -c '%g' /var/run/docker.sock)"
docker compose up --build
```

With Docker Desktop, start the service directly:

```powershell
docker compose up --build
```

Use the runtime endpoint to verify daemon access:

```bash
curl http://127.0.0.1:8000/api/v1/runtime
```

A healthy response includes `"available": true` and the host Docker daemon version. Stop and
remove the service container with:

```bash
docker compose down
```

## Tool Domains

The service is a thin tool adapter, not a benchmark planner or policy engine. Topology APIs return pure facts;
`runtime.service_capabilities` returns fixed read-only operation evidence; generic `operation.*` tools perform one
typed project/service-scoped action. LLM calls, `available_faults`, fault meaning, candidate authorization,
session policy, qualification, recovery planning, and scoring live in Benchmark Agent and its Adapter.

Tools are grouped into packages under `seedemu_tool_service/tools/`. Each domain exposes one
registration function that binds its functions or methods to the shared `ToolRegistry`.

The network-domain skeleton is organized as follows:

```text
tools/network/
|-- models.py        # Explicit argument and result models
|-- tools.py         # Tool function or bound-method implementations
`-- registration.py  # Tool metadata and registry bindings
```

The initial network tools are:

- `network.inspect_ip_address`: normalize an IPv4 or IPv6 address and inspect its properties.
- `network.ping`: execute ICMP echo requests inside a selected emulated source container and
  report whether the target host is reachable.

Both demonstrate bound methods, explicit Pydantic argument validation, domain registration,
discovery, and registry invocation. Each registration associates a handler with an argument model.
The registry derives the tool's input JSON Schema from that model, while the result model defines
the stable output contract.

The ping command is passed to Docker as an argument vector rather than through a shell. New network
tools should follow the same pattern and be added to `register_network_tools()`.

### DNS Domain

The DNS-domain skeleton follows the same structure:

```text
tools/dns/
|-- models.py        # DNS argument and result models
|-- tools.py         # DNS tool implementations
`-- registration.py  # DNS registry bindings
```

The initial `dns.lookup` tool runs `dig` inside a selected emulated container. It uses the node's
configured resolver by default or an explicitly supplied DNS server. The source container must have
the `dig` executable installed.

### BGP Domain

The BGP-domain skeleton lives under `tools/bgp/` and includes explicit argument and result models,
bound-method implementations, and registry bindings. Its reference tool is `bgp.summary`, which
runs `vtysh -c "show bgp ipv4 unicast summary"` inside a selected emulated router. The router
container must provide `vtysh` and a compatible routing daemon.

### PKI Domain

The PKI-domain skeleton lives under `tools/pki/`. It is organized by tool category so certificate
inspection, remote TLS inspection, trust verification, and expiration checks can evolve separately.
The source container must provide `openssl`, and supplied paths are interpreted inside that
container.

The initial PKI tools are read-only diagnostics for certificate and TLS service state:

- `pki.inspect_certificate_file`: inspect an X.509 certificate file inside an emulated node and
  return both OpenSSL output and parsed subject, issuer, validity, serial, and SHA-256 fingerprint
  fields when present.
- `pki.inspect_certificate_names`: inspect a certificate subject and subjectAltName extension.
- `pki.inspect_certificate_extensions`: inspect common X.509 extensions such as key usage,
  extended key usage, basic constraints, and subjectAltName.
- `pki.inspect_certificate_public_key`: inspect the public-key algorithm and key size embedded in
  a certificate.
- `pki.get_certificate_fingerprint`: return a certificate fingerprint using SHA-1, SHA-256, or
  SHA-512.
- `pki.inspect_remote_tls_certificate`: connect from an emulated node to a TLS service with
  `openssl s_client`, optionally using SNI, and inspect the certificate presented by the service.
  The source container must provide `timeout` and `openssl`.
- `pki.verify_certificate_chain`: run `openssl verify` inside an emulated node to check whether a
  certificate chains to supplied CA material.
- `pki.check_certificate_expiration`: run `openssl x509 -checkend` inside an emulated node to
  determine whether a certificate is expired or will expire within a warning window.

These tools support service-diagnosis and security-response tasks where network connectivity is
available but HTTPS/TLS trust, certificate deployment, or certificate expiration may be the root
cause of failure.
