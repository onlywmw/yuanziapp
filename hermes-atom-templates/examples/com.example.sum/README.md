# Sum Atom

计算两个数的和。

## Run

```bash
python3 server.py
```

## Call

```bash
curl -X POST http://127.0.0.1:18080/run \
  -H "Content-Type: application/json" \
  -d '{"a": 3, "b": 5}'
```

## Test

```bash
pytest tests/
```
