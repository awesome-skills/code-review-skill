# ML / Data Science Code Review Guide

> Review guide for machine-learning and data-science code in the Python stack (scikit-learn, pandas, NumPy, PyTorch, Jupyter). It covers the bugs that make up most ML defects: data leakage, flawed evaluation, irreproducible results, silent pandas/NumPy errors, training-loop mistakes, train/serve skew, and notebook hidden state. ML bugs rarely crash. They show up as a number that looks too good, so this guide ends with small checks that **prove** a suspected bug instead of guessing at it.

## Table of Contents

- [Data Leakage](#data-leakage)
- [Evaluation](#evaluation)
- [Reproducibility](#reproducibility)
- [pandas & NumPy Pitfalls](#pandas--numpy-pitfalls)
- [PyTorch Training Loops](#pytorch-training-loops)
- [Train/Serve Consistency & Model Files](#trainserve-consistency--model-files)
- [Notebooks](#notebooks)
- [Test-Driven Verification](#test-driven-verification)
- [Review Checklist](#review-checklist)
- [References](#references)

---

## Data Leakage

Leakage means information from the evaluation data, or from the future, reaches training. The model then scores well offline and fails in production. It is the most common reason ML results can't be reproduced, and it never raises an error.

### Split first, then fit every preprocessing step on the training set only

```python
# ❌ Bad — the scaler sees the test rows, so test statistics leak into training
X_scaled = StandardScaler().fit_transform(X)
X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2)

# ✅ Good — split first; a Pipeline fits the scaler on training data only
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, stratify=y, random_state=42
)
model = make_pipeline(StandardScaler(), LogisticRegression())
model.fit(X_train, y_train)
model.score(X_test, y_test)
```

The same rule applies to imputers, encoders, `TfidfVectorizer`, PCA, feature selection, and target encoding: anything with a `fit` step. Putting them in a `Pipeline` is the easiest way to make this correct by construction.

### Feature selection and resampling belong inside cross-validation

```python
# ❌ Bad — features are chosen using all labels, then "validated" with CV
X_sel = SelectKBest(f_classif, k=20).fit_transform(X, y)
cross_val_score(LogisticRegression(), X_sel, y, cv=5)   # optimistic score

# ❌ Bad — SMOTE before the split puts synthetic copies of test rows into training
X_res, y_res = SMOTE().fit_resample(X, y)
X_train, X_test, y_train, y_test = train_test_split(X_res, y_res)

# ✅ Good — every fitted step runs inside each fold, on that fold's training part only
from imblearn.pipeline import make_pipeline as make_imb_pipeline

pipe = make_imb_pipeline(
    StandardScaler(),
    SelectKBest(f_classif, k=20),
    SMOTE(random_state=42),
    LogisticRegression(max_iter=1000),
)
cross_val_score(pipe, X, y, cv=StratifiedKFold(5, shuffle=True, random_state=42))
```

How large the effect is: on **pure random noise** (100 rows, 5,000 features, random labels), the first version reports ~0.85 cross-validated accuracy; the pipeline version reports ~0.45, i.e. chance. The leaky version "finds" signal that does not exist.

Use `imblearn.pipeline` (not `sklearn.pipeline`) when the pipeline contains a resampler. It applies resampling during `fit` only, never to validation folds.

### Related rows must stay on the same side of the split

```python
# ❌ Bad — the same patient appears in train and test; the model memorizes patients
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

# ✅ Good — split by group so each patient is entirely in train or entirely in test
splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
train_idx, test_idx = next(splitter.split(X, y, groups=df["patient_id"]))
```

Ask what one real-world "unit" is: a user, patient, session, document, or image source. Random row splits leak whenever one unit has several rows. Use `GroupKFold` / `StratifiedGroupKFold` for cross-validation.

### Time-ordered data needs a time-ordered split

```python
# ❌ Bad — shuffled split trains on next month to predict last month
X_train, X_test, y_train, y_test = train_test_split(X, y, shuffle=True)

# ✅ Good — train on the past, evaluate on the future
cutoff = df["date"].quantile(0.8)
train, test = df[df["date"] <= cutoff], df[df["date"] > cutoff]

# for CV: each fold trains on earlier rows and validates on later ones
cv = TimeSeriesSplit(n_splits=5)
```

Rolling features need the same care: `df["sales"].rolling(7).mean()` includes the current row. If the target is today's sales, shift first: `df["sales"].shift(1).rolling(7).mean()`.

### Target leakage: features that are only known after the outcome

Look at every feature and ask: *would this value exist at the moment we make the prediction?*

```python
# ❌ Bad — predicting churn with fields that are filled in because the customer churned
features = ["tenure", "plan", "cancellation_reason", "refund_issued", "days_since_last_login"]

# ✅ Good — only information available at prediction time
features = ["tenure", "plan", "support_tickets_last_30d", "days_since_last_login"]
```

Warning signs: a single feature with very high importance, validation accuracy far above published baselines, or a column whose name describes an outcome (`*_status`, `*_reason`, `closed_at`, `resolution`).

### Duplicates across the split

Exact or near-duplicate rows (re-uploaded images, repeated records, augmented copies) in both train and test inflate scores. Deduplicate **before** splitting, and generate augmentations only from training rows.

---

## Evaluation

### The test set is used once, at the end

```python
# ❌ Bad — hyperparameters picked by test score; the test set has become a validation set
for C in [0.01, 0.1, 1, 10]:
    model = LogisticRegression(C=C).fit(X_train, y_train)
    print(C, model.score(X_test, y_test))

# ✅ Good — tune with CV on training data; touch the test set once
search = GridSearchCV(pipe, {"logisticregression__C": [0.01, 0.1, 1, 10]}, cv=5)
search.fit(X_train, y_train)
final_score = search.score(X_test, y_test)
```

The same applies to decision thresholds, early-stopping epochs, and feature choices. If any of these was chosen by looking at test results, the reported number is optimistic.

### Pick metrics that match the class balance and the cost of errors

```python
# ❌ Bad — 99% of transactions are legitimate; "always predict 0" scores 0.99
print(accuracy_score(y_test, y_pred))

# ✅ Good — compare against a trivial baseline and report imbalance-aware metrics
baseline = DummyClassifier(strategy="most_frequent").fit(X_train, y_train)
print("baseline:", baseline.score(X_test, y_test))
print(classification_report(y_test, y_pred))
print("PR-AUC:", average_precision_score(y_test, model.predict_proba(X_test)[:, 1]))
```

Request changes when a PR reports a metric without a baseline. "0.93 accuracy" means nothing until you know what a constant predictor scores.

### Stratify classification splits, and don't trust a single run

- Use `stratify=y` / `StratifiedKFold` so rare classes appear in every split.
- With small datasets, one split's score swings by several points. Report mean ± std over CV folds or several seeds before claiming one model beats another.
- A claimed improvement smaller than the run-to-run variation is not an improvement.

### Compute metrics on the right arrays

```python
# ❌ Bad — roc_auc_score needs scores/probabilities, not hard labels
roc_auc_score(y_test, model.predict(X_test))

# ✅ Good
roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
```

Also check the averaging mode for multi-class metrics (`average="macro"` vs `"weighted"` vs `"micro"`) and that it matches what the PR text claims.

---

## Reproducibility

### Seed every source of randomness

```python
# ❌ Bad — results change on every run; "it got better" may just be noise
model = RandomForestClassifier()
X_train, X_test, y_train, y_test = train_test_split(X, y)

# ✅ Good — fixed seeds for splits, models, and frameworks
SEED = 42

def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)  # seeds the CPU and all CUDA devices

seed_everything(SEED)
model = RandomForestClassifier(random_state=SEED)
X_train, X_test, y_train, y_test = train_test_split(X, y, random_state=SEED)
```

### DataLoader workers need their own seeding

```python
# ✅ Good — the pattern from the PyTorch reproducibility notes
def seed_worker(worker_id: int) -> None:
    worker_seed = torch.initial_seed() % 2**32
    np.random.seed(worker_seed)
    random.seed(worker_seed)

g = torch.Generator()
g.manual_seed(SEED)

loader = DataLoader(
    train_ds, batch_size=64, shuffle=True,
    num_workers=4, worker_init_fn=seed_worker, generator=g,
)
```

Without this, NumPy-based augmentations inside `__getitem__` can repeat across workers or differ between runs.

### Know what "deterministic" costs

`torch.use_deterministic_algorithms(True)` makes GPU runs repeatable but can slow training. On CUDA it also needs the `CUBLAS_WORKSPACE_CONFIG=:4096:8` environment variable. It is reasonable to leave it off for experiments, but the PR should say which mode produced its numbers.

### Pin what the result depends on

- Library versions (`requirements.txt` / lock file), because default hyperparameters change between releases.
- The exact data snapshot (a version, hash, or dated path), not "the latest export".
- The config that produced each reported number, committed next to the code.

---

## pandas & NumPy Pitfalls

### Chained assignment silently writes nowhere

```python
# ❌ Bad — the assignment goes to a temporary copy; df is unchanged.
# pandas 2.x warns (SettingWithCopyWarning / ChainedAssignmentError);
# with Copy-on-Write (default in pandas 3.0) it never modifies df.
df[df["age"] > 60]["senior"] = True

# ✅ Good — one .loc call selects rows and column together
df.loc[df["age"] > 60, "senior"] = True
```

The same applies to `subset = df[mask]` followed by `subset["col"] = ...`. Take an explicit `.copy()` when you mean to work on a separate frame.

### Merges can silently duplicate rows

```python
# ❌ Bad — if customers has duplicate customer_id rows, orders multiply silently
merged = orders.merge(customers, on="customer_id", how="left")

# ✅ Good — declare the expected relationship; pandas raises if it is violated
merged = orders.merge(customers, on="customer_id", how="left", validate="many_to_one")
assert len(merged) == len(orders)
```

Also check `how=`: an inner join silently drops rows that have no match, which can remove a whole class of examples.

### Missing values change dtypes and meaning

```python
# ❌ Bad — 0 is a real age; the model can't tell "missing" from "newborn"
df["age"] = df["age"].fillna(0)

# ❌ Bad — the median is computed on all rows, including test rows (leakage)
df["age"] = df["age"].fillna(df["age"].median())

# ✅ Good — impute inside the pipeline, and keep a missing-value indicator if missingness is informative
pipe = make_pipeline(SimpleImputer(strategy="median", add_indicator=True), model)
```

An integer column with any `NaN` becomes `float64`. Watch for code that later casts back with `astype(int)`. It raises on `NaN` (or, after a `fillna`, hides the missing values). Use the nullable `"Int64"` dtype if integers with gaps are needed.

### IDs and codes read as numbers

```python
# ❌ Bad — "00742" becomes 742; joins on zip/product codes then miss rows
df = pd.read_csv("customers.csv")

# ✅ Good — declare identifier columns as strings
df = pd.read_csv("customers.csv", dtype={"zip_code": str, "product_code": str})
```

### Broadcasting turns a shape mismatch into a wrong number

```python
# ❌ Bad — y_pred has shape (n, 1) and y_true has shape (n,).
# The subtraction broadcasts to (n, n); the "MSE" is wrong and nothing errors.
y_pred = model(X_tensor).detach().numpy()   # (n, 1)
mse = ((y_pred - y_true) ** 2).mean()

# ✅ Good — make the shapes match explicitly, and assert them
y_pred = model(X_tensor).detach().numpy().squeeze(-1)   # (n,)
assert y_pred.shape == y_true.shape, (y_pred.shape, y_true.shape)
mse = ((y_pred - y_true) ** 2).mean()
```

In PyTorch, `nn.MSELoss` only *warns* about this ("Using a target size that is different to the input size") and keeps training on the broadcast result. Treat that warning as a bug.

### Prefer vectorized operations over row-wise `apply`

`df.apply(f, axis=1)` and `iterrows()` run Python per row and are often 100× slower than column operations. It's not a correctness bug, but on large data it decides whether a pipeline finishes. Use column arithmetic, `np.where`, `.map`, or `groupby().transform` instead.

---

## PyTorch Training Loops

### The standard loop: four steps that are easy to miss

```python
# ❌ Bad
for epoch in range(epochs):
    for xb, yb in train_loader:
        loss = loss_fn(model(xb), yb)
        loss.backward()                 # gradients accumulate forever: no zero_grad
        optimizer.step()
        running_loss += loss            # keeps every batch's graph alive → memory grows

    for xb, yb in val_loader:           # dropout/batchnorm still in training mode
        val_loss += loss_fn(model(xb), yb)   # builds graphs: slow and memory-hungry

# ✅ Good
for epoch in range(epochs):
    model.train()
    for xb, yb in train_loader:
        xb, yb = xb.to(device), yb.to(device)
        optimizer.zero_grad()
        loss = loss_fn(model(xb), yb)
        loss.backward()
        optimizer.step()
        running_loss += loss.item()

    model.eval()
    with torch.no_grad():
        for xb, yb in val_loader:
            xb, yb = xb.to(device), yb.to(device)
            val_loss += loss_fn(model(xb), yb).item()
```

Check the `model.train()` call at the start of each epoch. A loop that calls `model.eval()` for validation and never switches back trains every later epoch with dropout off.

### Loss functions expect raw logits

```python
# ❌ Bad — CrossEntropyLoss applies log-softmax itself; this softmaxes twice
logits = model(xb)
loss = nn.CrossEntropyLoss()(torch.softmax(logits, dim=1), yb)

# ❌ Bad — sigmoid + BCELoss is numerically unstable for large logits
loss = nn.BCELoss()(torch.sigmoid(logits), yb)

# ✅ Good — pass raw logits; apply softmax/sigmoid only when you need probabilities
loss = nn.CrossEntropyLoss()(logits, yb)          # yb: class indices, dtype long
loss = nn.BCEWithLogitsLoss()(logits, yb.float())
```

Double softmax still trains, just worse, so it survives casual testing. Check the last layer of the model too. A `nn.Softmax` at the end of the model combined with `CrossEntropyLoss` is the same bug.

### Create new tensors on the input's device and dtype

```python
# ❌ Bad — works on CPU, fails (or silently moves data) on GPU
mask = torch.zeros(x.shape[0])

# ✅ Good
mask = torch.zeros(x.shape[0], device=x.device, dtype=x.dtype)
```

### Gradient accumulation must scale the loss

```python
# ✅ Good — divide so the accumulated gradient matches one large batch
loss = loss_fn(model(xb), yb) / accum_steps
loss.backward()
if (step + 1) % accum_steps == 0:
    optimizer.step()
    optimizer.zero_grad()
```

Without the division, the effective learning rate is `accum_steps` times larger than intended.

### Shuffle the training loader

`DataLoader(train_ds)` does not shuffle by default. If the dataset is stored sorted (by label, date, or source), every batch is one class and training stalls or oscillates. Training loaders should pass `shuffle=True` (or a sampler). Validation and test loaders don't need it.

---

## Train/Serve Consistency & Model Files

### Save the whole preprocessing + model pipeline, not just the model

```python
# ❌ Bad — serving code re-implements scaling and encoding by hand → train/serve skew
joblib.dump(clf, "model.joblib")

# ✅ Good — one artifact holds the fitted preprocessing and the model
joblib.dump(pipeline, "model.joblib")
```

For PyTorch, save normalization statistics, vocabularies, and label maps next to the `state_dict`, and load them from the same place in training and serving code.

### Feature order and schema

```python
# ❌ Bad — column order at inference depends on how the request dict was built
X = pd.DataFrame([request_features])

# ✅ Good — enforce the training schema
X = pd.DataFrame([request_features]).reindex(columns=TRAINING_COLUMNS)
assert not X.isna().any().any(), "missing features at inference"
```

### Loading model files executes code

`pickle.load`, `joblib.load`, and `torch.load(..., weights_only=False)` can run arbitrary code from the file. Flag any path where a model file comes from users, downloads, or shared storage outside your control.

```python
# ❌ Bad — opting out of the safe loader for a file you don't control
state = torch.load(downloaded_path, weights_only=False)

# ✅ Good — weights_only=True (the default since PyTorch 2.6) loads tensors only
state = torch.load(downloaded_path, weights_only=True)
model.load_state_dict(state)
```

Prefer `safetensors` for sharing weights.

---

## Notebooks

- **Hidden state:** cells run out of order can produce results the code no longer produces. Before trusting a notebook's numbers, confirm it was run top to bottom (Restart & Run All). Non-sequential execution counts (`[12]`, `[7]`, `[31]`) are the warning sign.
- **Committed outputs:** outputs can contain raw data, personal data, or tokens, and they make diffs unreadable. Expect stripped outputs (for example with `nbstripout`) unless the outputs *are* the deliverable.
- **Logic that should be a module:** training or preprocessing code that other code depends on belongs in a `.py` file that the notebook imports, so it can be tested and reviewed normally.
- **Machine-specific paths:** `/Users/alice/data/train.csv` breaks for every other reviewer. Use paths relative to the project or config.

---

## Test-Driven Verification

ML bugs produce plausible numbers, not stack traces. Before claiming a bug in review, prove it with a small check like the ones below. Each runs in seconds.

### Prove there is no overlap between splits

```python
def test_no_entity_overlap():
    train_ids = set(train_df["patient_id"])
    test_ids = set(test_df["patient_id"])
    assert train_ids.isdisjoint(test_ids), f"{len(train_ids & test_ids)} patients in both splits"
```

### Shuffled labels should score like the baseline

```python
# If the pipeline still beats the baseline with random labels, something leaks.
y_shuffled = np.random.default_rng(0).permutation(y_train)
score = cross_val_score(pipe, X_train, y_shuffled, cv=5).mean()
baseline = cross_val_score(DummyClassifier(), X_train, y_shuffled, cv=5).mean()
assert score <= baseline + 0.02, f"score {score:.3f} with shuffled labels: leakage?"
```

### Overfit one batch

```python
# A correct model + loss + label pipeline can drive loss near zero on one small batch.
xb, yb = next(iter(train_loader))
xb, yb = xb.to(device), yb.to(device)
model.train()
for _ in range(200):
    optimizer.zero_grad()
    loss = loss_fn(model(xb), yb)
    loss.backward()
    optimizer.step()
assert loss.item() < 0.05, f"cannot overfit one batch (loss={loss.item():.3f})"
```

If this fails, the bug is in the model, the loss, or the labels, not in the hyperparameters.

### Assert shapes at boundaries

A single `assert y_pred.shape == y_true.shape` before computing a metric would have caught the broadcasting bug above. Ask for these asserts in metric and loss code.

---

## Review Checklist

### Data Leakage

- [ ] Split happens before any fitted preprocessing (scaler, imputer, encoder, vectorizer, PCA)
- [ ] Fitted steps live in a `Pipeline`, so CV refits them per fold
- [ ] Feature selection and resampling (SMOTE etc.) run inside CV, never before the split
- [ ] Rows from the same entity (user/patient/session/source) never span train and test (`Group*` splitters)
- [ ] Time-ordered data uses a time-ordered split; rolling features are shifted
- [ ] Every feature is available at prediction time (no post-outcome fields)
- [ ] Data deduplicated before splitting; augmentations generated from training rows only

### Evaluation

- [ ] Test set used once; hyperparameters, thresholds, and early stopping chosen on validation/CV
- [ ] A trivial baseline (`DummyClassifier`/mean predictor) is reported alongside the model
- [ ] Metric fits the problem (PR-AUC/recall/F1 for imbalance, not accuracy alone)
- [ ] Probability metrics (ROC-AUC, PR-AUC, log loss) receive scores, not hard labels
- [ ] Classification splits are stratified; claimed gains exceed run-to-run variance

### Reproducibility

- [ ] Seeds set for `random`, NumPy, PyTorch, splitters, and models (`random_state`)
- [ ] DataLoader workers seeded (`worker_init_fn` + `generator`)
- [ ] Library versions and data snapshot pinned; config for each reported result committed

### pandas & NumPy

- [ ] No chained assignment; writes use `.loc[rows, col]` or an explicit `.copy()`
- [ ] Merges declare `validate=` and check row counts; join type (`how=`) is intentional
- [ ] Missing values imputed inside the pipeline, not with global statistics or magic numbers
- [ ] ID/code columns read as strings
- [ ] Prediction and target shapes asserted equal before metrics/losses

### PyTorch

- [ ] `optimizer.zero_grad()` every step; `loss.item()` used for logging
- [ ] `model.train()` / `model.eval()` switched correctly; evaluation under `torch.no_grad()`
- [ ] Losses get raw logits (`CrossEntropyLoss`, `BCEWithLogitsLoss`); no softmax/sigmoid before them
- [ ] New tensors created on `x.device` / `x.dtype`
- [ ] Gradient accumulation divides the loss by `accum_steps`
- [ ] Training loader shuffles

### Serving & Files

- [ ] The saved artifact includes preprocessing (pipeline or saved stats), not just the model
- [ ] Inference enforces the training column order and schema
- [ ] No `pickle`/`joblib`/`torch.load(weights_only=False)` on untrusted files

### Notebooks

- [ ] Notebook results come from a clean top-to-bottom run
- [ ] Outputs stripped (no data/PII/tokens committed); reusable logic moved to modules
- [ ] No machine-specific absolute paths

---

## References

- [scikit-learn: Common pitfalls and recommended practices](https://scikit-learn.org/stable/common_pitfalls.html) — data leakage, preprocessing inside pipelines, randomness
- [PyTorch: Reproducibility](https://pytorch.org/docs/stable/notes/randomness.html) — seeding, DataLoader workers, deterministic algorithms
- [PyTorch: `torch.load`](https://pytorch.org/docs/stable/generated/torch.load.html) — `weights_only` and loading untrusted files
- [pandas: Copy-on-Write](https://pandas.pydata.org/docs/user_guide/copy_on_write.html) — why chained assignment no longer works
- [imbalanced-learn: Pipeline](https://imbalanced-learn.org/stable/references/generated/imblearn.pipeline.Pipeline.html) — resampling inside cross-validation
- [Kapoor & Narayanan, *Leakage and the Reproducibility Crisis in ML-based Science*](https://reproducible.cs.princeton.edu/) — a survey of leakage types found across published research
