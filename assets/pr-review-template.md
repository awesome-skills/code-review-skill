# PR Review Template

Copy and use this template for your code reviews.

---

## Summary

[Brief overview of what was reviewed - 1-2 sentences]

**PR Size:** [Small/Medium/Large] (~X lines)
**Review Time:** [X minutes]

## Strengths

- [What was done well]
- [Good patterns or approaches used]
- [Improvements from previous code]

## Architecture & Performance

**Architecture Assessment**
- [ ] Separation of concerns — are responsibilities clearly divided?
- [ ] Module responsibilities — does each module have a single purpose?
- [ ] Dependency direction — do dependencies flow toward stability?
- [ ] Consistent with existing patterns and conventions

> See [Architecture Review Guide](../reference/architecture-review-guide.md) for detailed SOLID, anti-pattern, and coupling analysis.

**Performance Assessment**
- [ ] Algorithm complexity — any O(n²) or worse on large inputs?
- [ ] Memory impact — large allocations, leaks, unbounded growth?
- [ ] I/O impact — excessive API calls, unbatched writes, missing caching?
- [ ] Database queries — N+1 risks, missing indexes, unoptimized joins?

> See [Performance Review Guide](../reference/performance-review-guide.md) for comprehensive Web Vitals, N+1, and caching guidance.

## Required Changes

🔴 **[blocking]** [Issue description]
> [Code location or example]
> [Suggested fix or explanation]

🔴 **[blocking]** [Issue description]
> [Details]

## Important Suggestions

🟡 **[important]** [Issue description]
> [Why this matters]
> [Suggested approach]

## Minor Suggestions

🟢 **[nit]** [Minor improvement suggestion]

💡 **[suggestion]** [Alternative approach to consider]

## Learning Notes

📚 [Educational context worth sharing about X]

📚 [Background behind design decision Y]

## Security Considerations

- [ ] No hardcoded secrets
- [ ] Input validation present
- [ ] Authorization checks in place
- [ ] No SQL/XSS injection risks
- [ ] CSRF protection for state-changing operations
- [ ] Sensitive data not leaked in logs/errors
- [ ] Dependency vulnerabilities checked (npm audit / pip audit / cargo audit)

> See [Security Review Guide](../reference/security-review-guide.md) for comprehensive injection, XSS, CSRF, secrets, and auth checklist.

## Test Coverage

- [ ] Unit tests added/updated
- [ ] Edge cases covered
- [ ] Error cases tested

## Verdict

**[ ] ✅ Approve** - Ready to merge
**[ ] 💬 Comment** - Minor suggestions, can merge
**[ ] 🔄 Request Changes** - Must address blocking issues

---

## Quick Copy Templates

### Blocking Issue
```
🔴 **[blocking]** [Title]

[Description of the issue]

**Location:** `file.ts:123`

**Suggested fix:**
\`\`\`typescript
// Your suggested code
\`\`\`
```

### Important Suggestion
```
🟡 **[important]** [Title]

[Why this is important]

**Consider:**
- Option A: [description]
- Option B: [description]
```

### Minor Suggestion
```
🟢 **[nit]** [Suggestion]

Not blocking, but consider [improvement].
```

### Praise
```
🎉 **[praise]** Great work on [specific thing]!

[Why this is good]
```

### Learning
```
📚 **[learning]** [Educational note]

For context, [X] works this way because [Y]. No action needed — just sharing.
```
