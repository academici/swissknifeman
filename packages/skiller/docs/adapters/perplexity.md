# Adapter: Perplexity

Skills from `skills/imported/` are compatible with Perplexity Computer out of the box —
most of them came from the ecosystem Perplexity super-skills
(see `references/get-zeked-perplexity-super-skills.md`).

## Loading

In the interface Perplexity:

**Skills → Create skill → Upload `SKILL.md`**

Files are downloaded one at a time; snippets are inserted into the body if necessary
skill or downloaded as attachments.

## What to consider

- Perplexity does not read local directories - installation only via UI;
- upstream-tracked skills (`skills/imported/`) are updated via
  [upstream-sync](../guide/upstream-sync): after updating the registry, reboot
  file in Perplexity manually.
