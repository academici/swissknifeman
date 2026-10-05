# Query

Python stdlib-only approach for validating JSON against JSON Schema draft 2020-12 subset and rendering Markdown from templates with partials (string.Template vs vendoring a small library). Are there tiny vendorable pure-Python JSON Schema validators and minimal mustache implementations (e.g. chevron, pystache) suitable to vendor with MIT license?

# Answer

Short answer: for Markdown templates, vendor Chevron if you want Mustache sections and partials; use string.Template only for plain variable substitution. For Draft 2020-12 validation, I wouldn’t pick a small implementation based on “supports the draft” alone: I couldn’t verify a tiny, maintained, stdlib-only MIT validator with clear subset semantics. If you control the schema subset, a small validator you own may be more dependable than vendoring an obscure project; otherwise vendor jsonschema with its dependencies and explicitly constrain the accepted keywords.

## JSON Schema validation

The well-established Python option is . It advertises full Draft 2020-12 support, but it is not stdlib-only and is not a tiny single-file dependency. Its documentation also makes a useful distinction between validating instances and checking whether the schema itself is valid: use Draft202012Validator.check_schema(schema) for the latter.
I found a PyPI project named json-schema-tool that claims Draft 2020-12 support, but the results available here weren’t enough to verify its maintenance, exact subset coverage, dependency footprint, or license confidently. I would treat it as a candidate for inspection, not a recommendation.
If your schemas really are a fixed subset, define a closed profile—supported keywords, $ref scope, type semantics, and explicit behavior for unknown keywords—and fail closed on unsupported schema constructs. Draft 2020-12’s behavior includes details easy to miss in a handwritten validator: for example, format is annotation-oriented by default, while type: "integer" includes numbers with zero fractional part. Run your fixtures against the official , selecting the 2020-12 cases relevant to your profile; don’t claim full-draft compatibility if you only test a subset.

## Markdown templates

Chevron’s API supports rendering from strings and partials supplied through a dictionary or filesystem, so you can vendor the renderer and keep your templates as ordinary project files. For generated Markdown, I’d keep template data deliberately simple and avoid Mustache lambdas; that leaves a smaller behavior surface to test.

## Practical recommendation

- Need broad Draft 2020-12 behavior: vendor jsonschema and its required runtime dependencies, then pin the version and test your schema corpus.
- Need stdlib-only: implement a narrowly specified validator for your known schema profile, with a supported-keyword allowlist and official-suite fixtures for that profile. Don’t label it a general Draft 2020-12 validator.
- Need Markdown variables plus partials: vendor Chevron, include its MIT notice, and add a few rendering tests for escaping, missing keys, and partial resolution.
- Need only simple substitutions: string.Template is the leanest choice; partials can be assembled by your own small, explicit include step rather than adopting Mustache.

Sources:
1. [python-jsonschema/jsonschema](https://github.com/python-jsonschema/jsonschema)
2. [pypi](https://pypi.org/project/json-schema-tool/)
3. [JSON Schema Test Suite](https://github.com/json-schema-org/JSON-Schema-Test-Suite)
4. [Chevron](https://github.com/noahmorrison/chevron)
5. [Pystache](https://github.com/defunkt/pystache)
