# {{cookiecutter.name}}

{{cookiecutter.description}}

## Run

```bash
python3 server.py
```

## Call

```bash
curl -X POST http://127.0.0.1:{{cookiecutter.port}}/run \
  -H "Content-Type: application/json" \
  -d '@atom/examples/input.json'
```

## Test

```bash
pytest tests/
```
