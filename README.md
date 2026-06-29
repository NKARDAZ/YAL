# [YAL](https://pypi.org/project/yal-cmd/)

<img src="logo.svg" width="48" align="left" />

**YAL** is a command-line utility for project initialization and updates based
on templates from git repositories.

It also supports project-local commands (similar to Makefile targets or scripts
in package.json). Define them in `yal.toml` and invoke them with
`yal <command>`.

## Commands

- `yal new <kind>[:<name>][@<ref>] [--commit]` — uses a template to create a new
  project; if name is not specified, the `default` template will be used
- `yal update <kind>[:<name>] [--commit]` — downloads and caches the latest
  version of a template
- `yal add <kind>:<name>[@<ref>] from <repository URL | user/repo> [--commit]` —
  registers an external template from GitHub with the specified name
- `yal remove <kind>[:<name>[@<version>]]` — removes a template from the local
  storage; if name is not specified, all templates of the given kind will be
  removed

`--commit` (on `new`, `update`, `add`) skips release lookup entirely and
resolves against the latest matching commit instead — useful when a repository
has tagged releases but you specifically want unreleased work.

---

## Create a project

Downloads the template (if not cached locally) and initiates the configuration
process.

```bash
# Basic usage — uses the "default" template, latest version
yal new book

# Specify a template by name
yal new book:my-theme

# Specify a version (release tag or commit hash)
yal new book@1.7.1
yal new book@c651f7d

# Combined
yal new book:my-theme@1.7.1

# Skip releases, use the latest commit instead
yal new book --commit
```

If the requested version is already cached locally, YAL skips the download. If
no version is specified, YAL uses the most recent locally cached version; if
none is cached, it downloads the latest release (or the latest commit if the
repository has no releases). Pass `--commit` to skip the release lookup entirely
and resolve straight to the latest matching commit, even when releases exist.

---

## Update a template

Downloads and caches the latest version of a template without creating a
project. Useful for pre-caching before working offline.

```bash
yal update book
yal update book:my-theme

# Skip releases, update to the latest commit instead
yal update book --commit
```

---

## Add an external template

Registers a GitHub repository as a named template under a given kind, then
downloads it.

```bash
# Register and download the latest release (or commit)
yal add book:my-theme from https://github.com/user/my-book-template
# shortcut for GitHub
yal add book:my-theme from user/my-book-template
# or
yal add book:my-theme <other git service/local repo>

# Register a specific version
yal add book:my-theme@1.2.0 from user/my-book-template

# Skip releases, register and download the latest commit instead
yal add book:my-theme from user/my-book-template --commit
```

`<kind>:<name>` must not collide with a built-in template —
`yal add book:default from ...` is rejected, since `book:default` already ships
with YAL. Register under a different name instead (e.g. `book:my-theme`).

After registration the template is available like any built-in one:

```bash
yal new book:my-theme
yal update book:my-theme
```

Registered templates are stored in `~/.yal/user-templates.toml`. Downloaded
files go to `~/.yal/user-templates/<kind>/<name>/<version>/`.

## Git

You can use any Git hosting service or a local repository. Built-in shortcuts
are available for a number of services:

```bash
user/repo # Github
gitlab:user/repo
codeberg:user/repo
bitbucket:user/repo
git.gay:user/repo
gitverse:user/repo
sourceforge:project/repo
sourceforge:user@project/repo
```

```bash
yal add my-sf:default from sourceforge:my-project/code
```

Local repository:

```bash
yal add my-local-repos:default from /path/to/local/repo
```

---

## Remove a template

Removes cached template files from local storage. When all versions of a
user-registered template are removed, its registry entry is also deleted.

```bash
# Remove all cached versions of all "book" templates
yal remove book

# Remove all cached versions of a specific template
yal remove book:default
yal remove book:my-theme

# Remove a specific version only
yal remove book:default@1.7.1
yal remove book:my-theme@c651f7d
```

---

## yal.toml

A configuration file placed in the root of the created project. It stores
metadata about the template used and lets you define local commands for the
project.

```toml
[origin]
template         = "book"
template-version = "9670322"          # commit hash, or a release tag like "1.7.1"
created-at       = "2026-05-31T03:16:33Z"
yal-version      = "0.1.1"

[[command]]
name      = "make"
script    = "/build/build.py"         # leading "/" = project root, not filesystem root
exec      = "python3"
arguments = { --mode = [] }           # [] means any value is accepted
# yal make              → python3 build/build.py
# yal make --mode=print → python3 build/build.py --mode=print

[[command]]
name   = "make print"
macros = "make --mode=print"
# yal make print → expands to → yal make --mode=print
```

### Inline scripts

`script` doesn't have to be a path — it can contain the code itself as a
multi-line string. In that case `exec` is required (there's no file extension to
infer the interpreter from), and the code is passed directly to the interpreter
via its own "run code" flag (`-c`/`-e`/`-r`) — nothing is written to disk.

```toml
[[command]]
name = "hello"
exec = "python3"
script = """
def greet():
    print("Hello from an inline script!")

greet()
"""
```

Supported `exec` values for inline scripts: `python3`/`python`,
`node`/`ts-node`, `ruby`, `perl`, `php`, `bash`/`zsh`/`fish`/`sh`, `os-bash`,
`lua`. Arguments (`arguments = {...}`) work the same as with file scripts — with
one exception: `lua` doesn't support passing extra arguments to inline code (its
CLI always treats the first extra argument as a script file to run), so
`yal.toml` rejects arguments on `lua` inline scripts rather than silently
dropping them.

If `yal.toml` is not present in the template, it will be created automatically
with a default `[origin]` section filled in on project creation.

### Commands

Each `[[command]]` entry supports:

| Field       | Description                                                                                          |
| ----------- | ---------------------------------------------------------------------------------------------------- |
| `name`      | Command name as typed on the CLI (spaces allowed for multi-token names)                              |
| `script`    | Path to the script file. Leading `/` is relative to the project root                                 |
| `exec`      | Interpreter: `python3`, `node`, `bash`, `os-bash`, etc. Auto-detected from file extension if omitted |
| `arguments` | Allowed flags and their accepted values. Empty list `[]` accepts any value                           |
| `macros`    | Expands to another command instead of running a script                                               |

`exec = "os-bash"` uses `bash -c` on Unix and `cmd /c` on Windows.

Arguments are passed as `--key=value` or `--key value`:

```bash
yal make --mode=print
yal make --mode print
```

---

## yal.template.toml

A configuration file placed in the root of a template repository. When present,
YAL uses it to interactively prompt the user for values during `yal new`, then
applies them to target files in the new project.

```toml
[meta]
yal-min-version = "0.1.1"
post-commands   = ["npm install"]    # run after project is created
exclude         = ["examples/"]      # paths not copied into the project

[[fields]]
id             = "project-name"
type           = "text"
required       = true
is-folder-name = true                # this value becomes the output folder name

[[fields]]
id      = "author"
type    = "text"
default = "Anonymous"

[[fields]]
id      = "license"
type    = "select"
options = ["MIT", "Apache-2.0", "GPL-3.0"]
default = "MIT"

[messages]
project-name.prompt      = "Project name"
author.prompt            = "Author name"
author.placeholder       = "Your Name"
license.prompt           = "License"

[messages.ru]
project-name.prompt = "Название проекта"
author.prompt       = "Имя автора"
```

### Fields

Each `[[fields]]` entry supports:

| Field            | Description                                                                                                                                                                                  |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`             | Unique identifier, used as key in mappings and message lookups                                                                                                                               |
| `type`           | Input type: `text`, `number`, `list`, `select`, `multi-select`, or `boolean` (see Field types below)                                                                                                           |
| `required`       | If `true`, the user must provide a non-empty value (for `multi-select`, at least one item)                                                                                                   |
| `default`        | Default value used if the user presses Enter without typing. Use `"{placeholder}"` to mirror the placeholder. For `boolean`/`multi-select`, a native TOML `true`/`false` or array also works |
| `options`        | The list of choices — required for `select` and `multi-select`                                                                                                                               |
| `is-folder-name` | If `true`, the field's value becomes the name of the created project folder (only meaningful for `text`)                                                                                     |
| `min`            | Minimum value for `number` fields (inclusive)                                                                                                                                                |
| `max`            | Maximum value for `number` fields (inclusive)                                                                                                                                                |
| `pattern`        | Regular expression for `text` field validation (Python regex syntax, uses `re.fullmatch`)                                                                                                    |
| `allow-custom`   | If `true`, allows entering custom values in `select` and `multi-select` fields                                                                                                               |
| `min-cols`       | Minimum number of columns in interactive picker (default: 1). Only effective when terminal is wide enough                                                                                    |
| `show-if`        | Conditional expression to show/hide the field based on other fields (see Conditional fields below)                                                                                           |                                                                                |

### Field types

**`text`** — free-form input. `options`, if given, is just a hint and isn't enforced.

**`number`** — an integer or float.

**`list`** — one or more values, separated by commas.

**`select`** — exactly one value from `options`. In an interactive terminal this renders as an arrow-key picker (`↑`/`↓` to move, `Enter` to confirm); when stdin isn't a real terminal (pipes, CI), it falls back to typed input validated against `options`.

```toml
[[fields]]
id      = "license"
type    = "select"
options = ["MIT", "Apache-2.0", "GPL-3.0"]
default = "MIT"
```

**`multi-select`** — zero or more values from `options`, picked with `Space` to toggle and `Enter` to confirm (or comma-separated typed input as a fallback). The collected value is a list and is written natively to YAML/JSON/TOML targets; for `.env` targets it's joined with commas.

```toml
[[fields]]
id      = "features"
type    = "multi-select"
options = ["auth", "billing", "search"]
default = ["auth", "search"]   # or default = "auth,search"
```

**`boolean`** — a yes/no prompt (`[y/N]`/`[Y/n]` depending on `default`). Written as a native `true`/`false` to YAML/JSON/TOML, and as the string `"true"`/`"false"` to `.env`.

```toml
[[fields]]
id      = "use-ci"
type    = "boolean"
default = true
```

An unknown `type`, or a `select`/`multi-select` without `options`, falls back to plain text input with a warning — it won't crash project creation.

### Conditional fields

The `show-if` attribute lets you conditionally show or hide fields based on values of previously answered fields. It uses a simple expression language with logical operators.

**Supported operators:**
- Comparison: `==`, `!=`, `<`, `<=`, `>`, `>=`
- Membership: `in`, `not in`
- Logical: `and`, `or`, `not`
- Grouping: parentheses `( )`
- Truthiness: `field` alone checks for truthiness

**Examples:**

```toml
[[fields]]
id      = "use-ci"
type    = "boolean"
default = false

[[fields]]
id      = "ci-provider"
type    = "select"
options = ["github-actions", "gitlab-ci", "circle-ci"]
show-if = "use-ci"
# Only shown if use-ci is true

[[fields]]
id      = "enterprise-plan"
type    = "select"
options = ["basic", "pro", "enterprise"]
show-if = "features in ['enterprise']"
# Only shown if 'enterprise' is selected in the 'features' multi-select field

[[fields]]
id      = "deployment-type"
type    = "select"
options = ["dev", "staging", "production"]
show-if = "ci-provider == 'github-actions' and use-ci"
# Only shown for GitHub Actions CI
```

### Targets

After collecting field values, YAL writes them into files specified under
`[[targets]]`. Supported formats: `yaml`, `json`, `toml`, `env`.

```toml
[[targets]]
file   = "/config/meta.yaml"
format = "yaml"

  [[targets.fields]]
  key   = "project.name"          # dot-separated path
  field = "project-name"          # use value from [[fields]] id="project-name"

  [[targets.fields]]
  key   = "project.created"
  value = "${DATE}"               # built-in generator

  [[targets.fields]]
  key   = "project.uuid"
  value = "${UUID}"

  [[targets.fields]]
  key   = "meta.copyright"
  value = "© {author}, ${YEAR}"  # interpolation + generator

  [[targets.fields]]
  key   = "app.port"
  value = "${NULL}"              # sets YAML key to ~ (null), JSON to null
```

**Path syntax for nested keys:**
- project.name → sets project.name in the target file
- app[0].url → sets the first element's url field
- database[0] → sets the first element of the array

**Field mapping options:**
- field — use value from a [[fields]] entry by its id
- value — use a literal value or generator expression (e.g., "${DATE}", "© {author}")
- fallback — fallback value if the primary field or value resolves to empty ("", [], or None)

### .env file support

Target format env handles .env files:

```toml
[[targets]]
file   = "/.env"
format = "env"

  [[targets.fields]]
  key   = "APP_NAME"
  field = "project-name"

  [[targets.fields]]
  key   = "APP_PORT"
  field = "port"
```

YAL preserves comments and empty lines, updates existing variables in place, and adds new ones at the end. Values with spaces or special characters are automatically quoted.

### Built-in generators

| Syntax         | Output                          |
| -------------- | ------------------------------- |
| `${UUID}`      | Random UUID4                    |
| `${DATE}`      | Current date `YYYY-MM-DD` (UTC) |
| `${YEAR}`      | Current year                    |
| `${MONTH}`     | Current month                   |
| `${DAY}`       | Current day                     |
| `${TIMESTAMP}` | Unix timestamp (seconds)        |
| `${RANDOM}`    | Random integer 0 – 2³¹−1        |
| `${NULL}`      | Sets the YAML key to `~` (null) |

Field values can be interpolated with `{field-id}` syntax and combined freely
with generators: `"© {author}, ${YEAR}"`.

### Option localization and labels

For `select` and `multi-select` fields, you can localize option display names and add descriptions:

```toml
[messages]
genre.prompt = "Select book genre"
# genre.option."Fantasy"
genre.option.label."Fantasy" = "Magic, mythical creatures, imaginary worlds"
genre.option."Sci-Fi" = "Science Fiction"
genre.option.label."Sci-Fi" = "Future, technology, space exploration"
# genre.option."Mystery"
genre.option.label."Mystery" = "Crime, detective work, suspense"

[messages.ru]
genre.prompt = "Выберите жанр книги"
genre.option."Fantasy" = "Фэнтези"
genre.option.label."Fantasy" = "Магия, мифические существа, вымышленные миры"
genre.option."Sci-Fi" = "Научная фантастика"
genre.option.label."Sci-Fi" = "Будущее, технологии, космические путешествия"
genre.option."Mystery" = "Детектив"
genre.option.label."Mystery" = "Преступления, расследования, саспенс"
```

When displayed in the picker, options show both the display name and description:

```
Fantasy — Magic, mythical creatures, imaginary worlds
Science Fiction — Future, technology, space exploration
Mystery — Crime, detective work, suspense
```

The stored value remains the original option key (`"Fantasy"`, `"Sci-Fi"`, `"Mystery"`), not the display name.

### Localization

Messages support per-language overrides. YAL detects the system locale
automatically and falls back to the base (top-level) messages if no translation
is found for the current language.

```toml
[messages]
project-name.prompt = "Project name"    # base (fallback)

[messages.ru]
project-name.prompt = "Название проекта"
```

---

## Built-in templates

### &lt;Book&gt; Typst Book Template

- **Repo:** https://github.com/DemerNkardaz/Typst-Book-Template
- **Name:** `default`
- **Use:** `yal new book`

A template for creating a book using [Typst](https://typst.app/), including a
prebuilt structure, plugins, styles, settings, and a build system combining
Typst and Python tools.

**Requirements:** [Typst compiler](https://github.com/typst/typst/releases) and
the following Python packages:

```bash
pip install pyyaml pikepdf pillow
```

---

## Custom templates

Any public repository can be registered as a template. The repository does not
need to contain a `yal.template.toml` — YAL will copy it as-is and create a
default `yal.toml` in the resulting project.

```bash
# Register under a new kind "vue", name "default"
yal add vue:default from <user>/my-vue-template

# Create a project from it
yal new vue
```

You can register multiple named templates under the same kind:

```bash
yal add vue:tailwind from <user>/vue-tailwind-template
yal add vue:minimal  from <user>/vue-minimal-template

yal new vue:tailwind
yal new vue:minimal
```

### Full example with yal.template.toml

```toml
[meta]
yal-min-version = "0.1.3"
post-commands   = ["git init", "pip install -r requirements.txt"]

[[fields]]
id             = "book-title"
type           = "text"
required       = true
is-folder-name = true

[[fields]]
id      = "author"
type    = "text"
default = "{placeholder}"

[[fields]]
id      = "genre"
type    = "select"
options = ["fantasy", "scifi", "mystery", "romance"]
default = "fantasy"

[[fields]]
id      = "features"
type    = "multi-select"
options = ["glossary", "illustrations", "index", "bibliography"]
default = ["glossary", "bibliography"]

[[fields]]
id      = "use-typst"
type    = "boolean"
default = true

[[fields]]
id      = "output-format"
type    = "select"
options = ["pdf", "html", "epub"]
show-if = "use-typst"
default = "pdf"

[[targets]]
file   = "/book.yaml"
format = "yaml"

  [[targets.fields]]
  key   = "book.title"
  field = "book-title"

  [[targets.fields]]
  key   = "book.author"
  field = "author"

  [[targets.fields]]
  key   = "book.genre"
  field = "genre"

  [[targets.fields]]
  key   = "book.features"
  field = "features"

  [[targets.fields]]
  key   = "book.created"
  value = "${DATE}"

[[targets]]
file   = "/.env"
format = "env"

  [[targets.fields]]
  key   = "BOOK_TITLE"
  field = "book-title"

  [[targets.fields]]
  key   = "BOOK_AUTHOR"
  field = "author"

  [[targets.fields]]
  key   = "OUTPUT_FORMAT"
  field = "output-format"
  fallback = "pdf"

[messages]
book-title.prompt         = "Book title"
author.prompt             = "Author"
author.placeholder        = "Your Name"
genre.prompt              = "Select genre"
genre.option.fantasy      = "Fantasy"
genre.option.label.fantasy = "Magic, mythical creatures, imaginary worlds"
genre.option.scifi        = "Science Fiction"
genre.option.label.scifi  = "Future, technology, space exploration"
genre.option.mystery      = "Mystery"
genre.option.label.mystery = "Crime, detective work, suspense"
genre.option.romance      = "Romance"
genre.option.label.romance = "Love stories, relationships, emotions"
features.prompt           = "Select book features"
features.option.glossary  = "Glossary"
features.option.label.glossary = "Terms and definitions"
features.option.illustrations = "Illustrations"
features.option.label.illustrations = "Images and diagrams"
features.option.index     = "Index"
features.option.label.index = "Keyword index"
features.option.bibliography = "Bibliography"
features.option.label.bibliography = "References and sources"
use-typst.prompt          = "Use Typst for typesetting"
output-format.prompt      = "Output format"

[messages.ru]
book-title.prompt         = "Название книги"
author.prompt             = "Автор"
author.placeholder        = "Ваше имя"
genre.prompt              = "Выберите жанр"
genre.option.fantasy      = "Фэнтези"
genre.option.label.fantasy = "Магия, мифические существа, вымышленные миры"
genre.option.scifi        = "Научная фантастика"
genre.option.label.scifi  = "Будущее, технологии, космические путешествия"
genre.option.mystery      = "Детектив"
genre.option.label.mystery = "Преступления, расследования, саспенс"
genre.option.romance      = "Романтика"
genre.option.label.romance = "Любовные истории, отношения, эмоции"
features.prompt           = "Выберите элементы книги"
features.option.glossary  = "Глоссарий"
features.option.label.glossary = "Термины и определения"
features.option.illustrations = "Иллюстрации"
features.option.label.illustrations = "Изображения и диаграммы"
features.option.index     = "Индекс"
features.option.label.index = "Ключевые слова"
features.option.bibliography = "Библиография"
features.option.label.bibliography = "Ссылки и источники"
use-typst.prompt          = "Использовать Typst для вёрстки"
output-format.prompt      = "Формат вывода"
```

---

## Local storage layout

```
~/.yal/
  templates/                      # built-in template cache
    <kind>/
      <name>/
        <version>/
          yal-meta.json
          ...template files...

  user-templates/                 # user-registered template cache
    <kind>/
      <name>/
        <version>/
          yal-meta.json
          ...template files...

  user-templates.toml             # user registry (managed by yal add / yal remove)
```

`yal-meta.json` stores the kind, name, version, source type (`release` or
`commit`), repository URL, release date, and install date for each cached
template.

---

## Authentication

YAL supports using personal access tokens to access private repositories and to
reduce API rate limits.

- For provider HTTP APIs, YAL recognizes these environment variables:
  - `GITHUB_TOKEN` or `GH_TOKEN` — GitHub API
  - `GITLAB_TOKEN` or `GL_TOKEN` — GitLab API
  - `CODEBERG_TOKEN` or `FORGEJO_TOKEN` — Codeberg / Forgejo API

- For Git operations (`git ls-remote`, `git clone`) YAL will, when a token is
  available for the host, inject it into HTTPS URLs as a practical fallback.
  Supported variables for HTTPS auth include:
  - `BITBUCKET_TOKEN` — Bitbucket HTTPS access
  - `SOURCEFORGE_TOKEN` — SourceForge HTTPS access
  - `GITVERSE_TOKEN` — gitverse.ru HTTPS access
  - `GITGAY_TOKEN` — git.gay HTTPS access

Example exports (bash):

```bash
# GitHub (API)
export GITHUB_TOKEN=ghp_...

# GitLab (API)
export GITLAB_TOKEN=glpat-...

# Codeberg / Forgejo (API)
export CODEBERG_TOKEN=...

# Bitbucket / SourceForge / gitverse (clone via HTTPS)
export BITBUCKET_TOKEN=...
export SOURCEFORGE_TOKEN=...
export GITVERSE_TOKEN=...
```

Note: token injection into URLs is only performed for HTTPS remotes and only
when the corresponding environment variable is set. SSH remotes (`git@...`) are
left unchanged and use SSH keys.
