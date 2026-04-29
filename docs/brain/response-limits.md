# Per-Brain Response Limits

`data/{brain_id}/config.json` can limit that brain's normal chat replies:

```json
{
  "response": {
    "max_tokens": 180,
    "max_sentences": 1
  }
}
```

- `max_tokens`: passed to the model request for this brain as the provider-side output cap. Use `null` or remove it to keep the model default. If this value is too small, the provider can still cut the answer mid-reply.
- `max_sentences`: added to the system prompt as soft guidance and enforced after generation at complete sentence boundaries. Streaming replies stop emitting once the limit is reached. Use `null`, `0`, or remove it to disable this limit.
