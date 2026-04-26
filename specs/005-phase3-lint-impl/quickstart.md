# Quickstart: Phase 3 階段二 — `ks lint` 真實實作

## 0. Setup

```bash
mise install
uv sync
make fixtures
export HKS_EMBEDDING_MODEL=simple
export KS_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/hks-lint.XXXXXX")
```

## 1. 建立乾淨 runtime

```bash
uv run ks ingest tests/fixtures/valid
uv run ks lint | jq .
```

預期：

- exit `0`
- `trace.steps[0].kind == "lint_summary"`
- `trace.steps[0].detail.findings == []`
- `trace.steps[0].detail.severity_counts.error == 0`

## 2. 製造 wiki orphan / dead-link

```bash
cp "$KS_ROOT/wiki/pages/project-atlas.md" "$KS_ROOT/wiki/pages/orphan-page.md"
uv run ks lint | jq '.trace.steps[0].detail.findings[] | select(.category=="orphan_page")'

rm "$KS_ROOT/wiki/pages/project-atlas.md"
uv run ks lint | jq '.trace.steps[0].detail.findings[] | select(.category=="dead_link")'
```

預期：

- `orphan_page` severity 為 `warning`
- `dead_link` severity 為 `warning`
- 無 `--strict` 時 exit 仍為 `0`

## 3. 製造 manifest mismatch

```bash
python - <<'PY'
import json, os, pathlib
root = pathlib.Path(os.environ["KS_ROOT"])
path = root / "manifest.json"
payload = json.loads(path.read_text())
first = next(iter(payload["entries"].values()))
first["derived"]["wiki_pages"].append("missing-page")
first["derived"]["vector_ids"].append("missing-vector-id")
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
PY

uv run ks lint | jq '.trace.steps[0].detail.findings[] | select(.severity=="error")'
```

預期：

- 出現 `manifest_wiki_mismatch`
- 出現 `manifest_vector_mismatch`
- 預設 exit `0`

## 4. Strict mode

```bash
uv run ks lint --strict
echo $?

uv run ks lint --strict --severity-threshold=warning
echo $?
```

預期：

- 有 error finding 時 `--strict` exit `1`
- 只有 warning finding 時，預設 threshold `error` 不 fail；threshold `warning` 會 fail
- stdout 仍為合法 JSON

## 5. Fix dry-run 與 apply

```bash
uv run ks lint --fix | jq '.trace.steps[0].detail | {planned: .fixes_planned, applied: .fixes_applied, skipped: .fixes_skipped}'
find "$KS_ROOT" -type f -print0 | sort -z | xargs -0 shasum -a 256 > "${TMPDIR:-/tmp}/hks-lint-before.sha"
uv run ks lint --fix | jq -e '.trace.steps[0].detail.fixes_applied == []'
find "$KS_ROOT" -type f -print0 | sort -z | xargs -0 shasum -a 256 > "${TMPDIR:-/tmp}/hks-lint-after.sha"
diff -u "${TMPDIR:-/tmp}/hks-lint-before.sha" "${TMPDIR:-/tmp}/hks-lint-after.sha"

uv run ks lint --fix=apply | jq '.trace.steps[0].detail | {applied: .fixes_applied, skipped: .fixes_skipped}'
tail -n 20 "$KS_ROOT/wiki/log.md"
```

預期：

- dry-run 不改任何檔案
- apply 只套用許可清單 action
- `wiki/log.md` 追加 `lint | lint_fix_applied`
- manifest / raw_sources / wiki pages 不被刪改

## 6. Error paths

```bash
KS_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/hks-lint-empty.XXXXXX") uv run ks lint
echo $?

uv run ks lint --severity-threshold=garbage
echo $?
```

預期：

- 未初始化 `/ks/` exit `66`，stderr 首行 `[ks:lint] error:`
- illegal flag value exit `2`，stderr 首行 `[ks:lint] usage:`
- 兩者 stdout 都是合法 `QueryResponse`

## 7. Regression gate

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```
