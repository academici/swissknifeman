<!-- Source: anonymized production project -->

# Before / After: tone and language

Couples «bad/good» for the code comment and commit title. One principle:
in Russian, about the reason, without bureaucracy, with a completed action.

## Comment in code

### Bad

```php
// This method filters records and returns the result.
public function publicList(): Collection
{
    return Document::query()->where('status', Status::Active)->get();
}
```

Why it’s bad: clerical («carries out», «produces»), retelling of what is already
can be seen from the code, but the main thing is not said: *why* filter by status.

### Okay

```php
public function publicList(): Collection
{
    // We limited the selection to active records so as not to drag the archive into the public list.
    return Document::query()->where('status', Status::Active)->get();
}
```

Why it's good: the comment is short, in Russian, explains the intention and consequence,
rather than duplicating code.

## Test description

### Bad

```php
// Transliteration of the method name, English, says nothing about the behavior:
it('test public list filter active', function () { /* ... */ });
```

### Okay

```php
// In Russian, about behavior and condition:
it('public list gives only active documents and hides the archive', function () {
    /* ... */
});
```

## Commit header

### Bad

```text
fix(api): fix filtering of documents in the public list
```

Why is it bad: bare infinitive («fix»), no body with the reason.
The format is correct - the problem is the tone.

### Okay

```text
fix(api): fixed filtering of documents in the public list

Archived records were included in public output - added a filter by status Active.
```

Why it's good: completed action («fixed»), body explains what was wrong
and what has changed. Type, scope and breaking-we take the markup from `git-commit-rules`.
