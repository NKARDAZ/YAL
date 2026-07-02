# [YAL](https://pypi.org/project/yal-cmd/)

<img src="https://raw.githubusercontent.com/NKARDAZ/YAL/main/logo.svg" width="48" align="left" />

**YAL** is a command-line utility for project initialization and updates based
on templates from git repositories.

It also supports project-local commands (similar to Makefile targets or scripts
in package.json). Define them in `.yal/project.yml` and invoke them with
`yal <command>`.

---

## Installation

```bash
pip install yal-cmd
```

> **Requires Python >= 3.12**

> **Dependencies:**
>
> - [requests](https://pypi.org/project/requests) >=2.34.2
> - [ruamel.yaml](https://pypi.org/project/ruamel.yaml) >=0.19.1
> - [tomli-w](https://pypi.org/project/tomli-w/) >=1.2.0

---

## Quick Start

```bash
# Create a project from the built-in book template
yal new book
```

YAL downloads the template (once — it’s cached afterward), then walks you
through a few interactive prompts (defined by the template’s
`.yal/template.yml`): project name, author, license, and so on. Answer them, and
a new folder appears — named after your project, or `book-<version>` if the
template doesn’t define a custom name.

```bash
cd book-1.7.1   # or whatever you named it
```

That’s the whole loop. The new folder contains a `.yal/project.yml` recording
which template and version it came from.

### Don’t have a template? Use any repo as one

You don’t need a `.yal/template.yml` to get started — any git repository works,
even an empty one:

```bash
yal add demo:my-app from <user>/my-repo
yal new demo:my-app
```

Without a `.yal/template.yml`, YAL just copies the repo as-is and creates a
default `.yal/project.yml` for you. Add field prompts and file templating later,
once you actually need them — see [.yal/template.yml](#yaltemplateyml) below.

### Running project commands

If the resulting `.yal/project.yml` has `[[command]]` entries (your own, or ones
shipped by the template), run them the same way you ran `yal new`:

```bash
yal <command-name>
```

See [.yal/project.yml](#yalyml) for how to define them.

---

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
# Basic usage — uses the “default” template, latest version
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
# Remove all cached versions of all “book” templates
yal remove book

# Remove all cached versions of a specific template
yal remove book:default
yal remove book:my-theme

# Remove a specific version only
yal remove book:default@1.7.1
yal remove book:my-theme@c651f7d
```

---

## .yal/project.yml

A configuration file placed in the root of the created project. It stores
metadata about the template used and lets you define local commands for the
project.

```yaml
origin:
  template: book
  template-version: '9670322' # commit hash, or a release tag like "1.7.1"
  created-at: '2026-05-31T03:16:33Z'
  yal-version: '0.1.1'

command:
  - name: make
    script: /build/build.py # leading "/" = project root, not filesystem root
    exec: python3
    arguments: # {} means any value is accepted
      --mode: []
    # yal make              → python3 build/build.py
    # yal make --mode=print → python3 build/build.py --mode=print

  - name: make print
    macros: make --mode=print
    # yal make print → expands to → yal make --mode=print
```

### Inline scripts

`script` doesn’t have to be a path — it can contain the code itself as a
multi-line string. In that case `exec` is required (there’s no file extension to
infer the interpreter from), and the code is passed directly to the interpreter
via its own "run code" flag (`-c`/`-e`/`-r`) — nothing is written to disk.

```yaml
command:
  - name: hello
    exec: python3
    script: |
      def greet():
          print("Hello from an inline script!")

      greet()
```

Supported `exec` values for inline scripts: `python3`/`python`,
`node`/`ts-node`, `ruby`, `perl`, `php`, `bash`/`zsh`/`fish`/`sh`, `os-bash`,
`lua`. Arguments (`arguments = {...}`) work the same as with file scripts — with
one exception: `lua` doesn’t support passing extra arguments to inline code (its
CLI always treats the first extra argument as a script file to run), so
`.yal/project.yml` rejects arguments on `lua` inline scripts rather than
silently dropping them.

If `.yal/project.yml` is not present in the template, it will be created
automatically with a default `[origin]` section filled in on project creation.

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

## .yal/template.yml

A configuration file placed in the root of a template repository. When present,
YAL uses it to interactively prompt the user for values during `yal new`, then
applies them to target files in the new project.

```yaml
meta:
  yal-min-version: '0.1.3'
  exclude: ['examples/'] # paths not copied into the project

actions:
  pre:
    - cmd: echo "Preparing project..."
    - cmd: mkdir -p .temp
  post:
    - cmd: git init --initial-branch=main
    - cmd: npm install
      if: use-npm
    - cmd: code "{project_path}"
      if: open-in-code
      os: windows

fields:
  - id: project-name
    type: text
    required: true
    is-folder-name: true # this value becomes the output folder name

  - id: author
    type: text
    default: Anonymous

  - id: license
    type: select
    options: ['MIT', 'Apache-2.0', 'GPL-3.0']
    default: MIT

  - id: use-npm
    type: boolean
    default: false

  - id: open-in-code
    type: boolean
    default: false

messages:
  project-name:
    prompt: Project name
  author:
    prompt: Author name
    placeholder: Your Name
  license:
    prompt: License
  use-npm:
    prompt: Install npm dependencies?
  open-in-code:
    prompt: Open project in VS Code?

  ru:
    project-name:
      prompt: Название проекта
    author:
      prompt: Имя автора
    use-npm:
      prompt: Установить npm зависимости?
    open-in-code:
      prompt: Открыть проект в VS Code?
```

### Actions

The `actions` section defines commands to run before and after project creation.
Commands support conditional execution and OS-specific filtering.

**Structure:**

```yaml
actions:
  pre:
    - cmd: echo "Starting..."
    - cmd: mkdir -p temp
  post:
    - cmd: git init --initial-branch=main
    - cmd: npm install
      if: use-npm
    - cmd: code "{project_path}"
      if: open-in-code
      os: windows
```

**Fields:**

| Field  | Description                                                     |
| ------ | --------------------------------------------------------------- |
| `pre`  | Commands executed before interactive field collection           |
| `post` | Commands executed after project creation                        |
| `cmd`  | The command to run (supports `{field}` interpolation)           |
| `if`   | Condition expression (same syntax as `show-if`)                 |
| `os`   | Restrict command to specific OS: `windows`, `linux`, or `macos` |

**Conditional commands:**

```yaml
actions:
  post:
    - cmd: npm install
      if: use-npm
    - cmd: pip install -r requirements.txt
      if: use-python
    - cmd: code "{project_path}"
      if: open-in-code and project-name != ""
```

**OS-specific commands:**

```yaml
actions:
  post:
    - cmd: timeout /t 1 /nobreak > nul && code "{project_path}"
      os: windows
      if: open-in-code
    - cmd: sleep 1 && code "{project_path}"
      os: linux
      if: open-in-code
    - cmd: sleep 1 && code "{project_path}"
      os: macos
      if: open-in-code
```

**Special variables:**

- `{project_path}` — absolute path to the created project folder

### Fields

Each `[[fields]]` entry supports:

| Field            | Description                                                                                                                                                                                  |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`             | Unique identifier, used as key in mappings and message lookups                                                                                                                               |
| `type`           | Input type: `text`, `number`, `list`, `select`, `multi-select`, or `boolean` (see Field types below)                                                                                         |
| `required`       | If `true`, the user must provide a non-empty value (for `multi-select`, at least one item)                                                                                                   |
| `default`        | Default value used if the user presses Enter without typing. Use `"{placeholder}"` to mirror the placeholder. For `boolean`/`multi-select`, a native TOML `true`/`false` or array also works |
| `options`        | The list of choices — required for `select` and `multi-select`                                                                                                                               |
| `is-folder-name` | If `true`, the field’s value becomes the name of the created project folder (only meaningful for `text`)                                                                                     |
| `min`            | Minimum value for `number` fields (inclusive)                                                                                                                                                |
| `max`            | Maximum value for `number` fields (inclusive)                                                                                                                                                |
| `pattern`        | Regular expression for `text` field validation (Python regex syntax, uses `re.fullmatch`)                                                                                                    |
| `allow-custom`   | If `true`, allows entering custom values in `select` and `multi-select` fields                                                                                                               |
| `min-cols`       | Minimum number of columns in interactive picker (default: 1). Only effective when terminal is wide enough                                                                                    |
| `show-if`        | Conditional expression to show/hide the field based on other fields (see Conditional fields below)                                                                                           |

### Field types

**`text`** — free-form input. `options`, if given, is just a hint and isn’t
enforced.

**`number`** — an integer or float.

**`list`** — one or more values, entered one per line (press `Enter` after each, then an empty line to finish).

```yaml
fields:
  - id: keywords
    type: list
    default: ['typst', 'book', 'publishing']
```

**`select`** — exactly one value from `options`. In an interactive terminal this
renders as an arrow-key picker (`↑`/`↓` to move, `Enter` to confirm); when stdin
isn’t a real terminal (pipes, CI), it falls back to typed input validated
against `options`.

```yaml
fields:
  - id: license
    type: select
    options: ['MIT', 'Apache-2.0', 'GPL-3.0']
    default: MIT
```

**`multi-select`** — zero or more values from `options`, picked with `Space` to
toggle and `Enter` to confirm (or comma-separated typed input as a fallback).
The collected value is a list and is written natively to YAML/JSON/TOML targets;
for `.env` targets it’s joined with commas.

```yaml
fields:
  - id: features
    type: multi-select
    options: ['auth', 'billing', 'search']
    default: ['auth', 'search'] # or default: "auth,search"
```

**`boolean`** — a yes/no prompt (`[y/N]`/`[Y/n]` depending on `default`).
Written as a native `true`/`false` to YAML/JSON/TOML, and as the string
`"true"`/`"false"` to `.env`.

```yaml
fields:
  - id: use-ci
    type: boolean
    default: true
```

An unknown `type`, or a `select`/`multi-select` without `options`, falls back to
plain text input with a warning — it won’t crash project creation.

### Conditional fields

The `show-if` attribute lets you conditionally show or hide fields based on
values of previously answered fields. It uses a simple expression language with
logical operators.

**Supported operators:**

- Comparison: `==`, `!=`, `<`, `<=`, `>`, `>=`
- Membership: `in`, `not in`
- Logical: `and`, `or`, `not`
- Grouping: parentheses `( )`
- Truthiness: `field` alone checks for truthiness

**Examples:**

```yaml
fields:
  - id: use-ci
    type: boolean
    default: false

  - id: ci-provider
    type: select
    options: ['github-actions', 'gitlab-ci', 'circle-ci']
    show-if: use-ci
    # Only shown if use-ci is true

  - id: enterprise-plan
    type: select
    options: ['basic', 'pro', 'enterprise']
    show-if: features in ['enterprise']
    # Only shown if 'enterprise' is selected in the 'features' multi-select field

  - id: deployment-type
    type: select
    options: ['dev', 'staging', 'production']
    show-if: ci-provider == 'github-actions' and use-ci
    # Only shown for GitHub Actions CI
```

### Targets

After collecting field values, YAL writes them into files specified under
`[[targets]]`. Supported formats: `yaml`, `json`, `toml`, `env`.

```yaml
targets:
  - file: /config/meta.yaml
    format: yaml
    fields:
      - key: project.name # dot-separated path
        field: project-name # use value from fields id="project-name"

      - key: project.created
        value: ${DATE} # built-in generator

      - key: project.uuid
        value: ${UUID}

      - key: meta.copyright
        value: '© {author}, ${YEAR}' # interpolation + generator

      - key: app.port
        value: ${NULL} # sets YAML key to ~ (null), JSON to null
```

**Path syntax for nested keys:**

- project.name → sets project.name in the target file
- app[0].url → sets the first element’s url field
- database[0] → sets the first element of the array

**Field mapping options:**

- field — use value from a [[fields]] entry by its id
- value — use a literal value or generator expression (e.g., "${DATE}", "©
  {author}")
- fallback — fallback value if the primary field or value resolves to empty ("",
  [], or None)

### .env file support

Target format env handles .env files:

```yaml
targets:
  - file: /.env
    format: env
    fields:
      - key: APP_NAME
        field: project-name

      - key: APP_PORT
        field: port
```

YAL preserves comments and empty lines, updates existing variables in place, and
adds new ones at the end. Values with spaces or special characters are
automatically quoted.

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

For `select` and `multi-select` fields, you can localize option display names
and add descriptions:

```yaml
messages:
  genre:
    prompt: Select book genre
    option:
      Fantasy: Fantasy
      Sci-Fi: Science Fiction
      Mystery: Mystery

      label:
        Fantasy: Magic, mythical creatures, imaginary worlds
        Sci-Fi: Future, technology, space exploration
        Mystery: Crime, detective work, suspense

  ru:
    genre:
      prompt: Выберите жанр книги
      option:
        Fantasy: Фэнтези
        Sci-Fi: Научная фантастика
        Mystery: Детектив

        label:
          Fantasy: Магия, мифические существа, вымышленные миры
          Sci-Fi: Будущее, технологии, космические путешествия
          Mystery: Преступления, расследования, саспенс
```

When displayed in the picker, options show both the display name and
description:

```
Fantasy — Magic, mythical creatures, imaginary worlds
Science Fiction — Future, technology, space exploration
Mystery — Crime, detective work, suspense
```

The stored value remains the original option key (`"Fantasy"`, `"Sci-Fi"`,
`"Mystery"`), not the display name.

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
need to contain a `.yal/template.yml` — YAL will copy it as-is and create a
default `.yal/project.yml` in the resulting project.

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

### Full example with .yal/template.yml

```yaml
meta:
  yal-min-version: '0.1.3'

actions:
  pre:
    - cmd: echo "Initializing project..."
  post:
    - cmd: git init --initial-branch=main
    - cmd: pip install -r requirements.txt
      if: use-python
    - cmd: npm install
      if: use-npm
    - cmd: code "{project_path}"
      if: open-in-code
      os: windows
    - cmd: sleep 1 && code "{project_path}"
      if: open-in-code
      os: linux
    - cmd: sleep 1 && code "{project_path}"
      if: open-in-code
      os: macos

fields:
  - id: book-title
    type: text
    required: true
    is-folder-name: true

  - id: author
    type: text
    default: '{placeholder}'

  - id: genre
    type: select
    options:
      - fantasy
      - scifi
      - mystery
      - romance
    default: fantasy

  - id: features
    type: multi-select
    options:
      - glossary
      - illustrations
      - index
      - bibliography
    default:
      - glossary
      - bibliography

  - id: use-typst
    type: boolean
    default: true

  - id: use-python
    type: boolean
    default: false

  - id: use-npm
    type: boolean
    default: false

  - id: open-in-code
    type: boolean
    default: false

  - id: output-format
    type: select
    options: ['pdf', 'html', 'epub']
    show-if: use-typst
    default: pdf

targets:
  - file: /book.yaml
    format: yaml
    fields:
      - key: book.title
        field: book-title

      - key: book.author
        field: author

      - key: book.genre
        field: genre

      - key: book.features
        field: features

      - key: book.created
        value: ${DATE}

  - file: /.env
    format: env
    fields:
      - key: BOOK_TITLE
        field: book-title

      - key: BOOK_AUTHOR
        field: author

      - key: OUTPUT_FORMAT
        field: output-format
        fallback: pdf

messages:
  book-title:
    prompt: Book title
  author:
    prompt: Author
    placeholder: Your Name
  genre:
    prompt: Select genre
    option:
      fantasy: Fantasy
      scifi: Science Fiction
      mystery: Mystery
      romance: Romance

      label:
        fantasy: Magic, mythical creatures, imaginary worlds
        scifi: Future, technology, space exploration
        mystery: Crime, detective work, suspense
        romance: Love stories, relationships, emotions
  features:
    prompt: Select book features
    option:
      glossary: Glossary
      illustrations: Illustrations
      index: Index
      bibliography: Bibliography

      label:
        glossary: Terms and definitions
        illustrations: Images and diagrams
        index: Keyword index
        bibliography: References and sources
  use-typst:
    prompt: Use Typst for typesetting
  use-python:
    prompt: Use Python dependencies?
  use-npm:
    prompt: Use npm dependencies?
  open-in-code:
    prompt: Open project in VS Code?
  output-format:
    prompt: Output format
  
  ru:
    book-title:
      prompt: Название книги
    author:
      prompt: Автор
      placeholder: Ваше имя
    genre:
      prompt: Выберите жанр
      option:
        fantasy: Фэнтези
        scifi: Научная фантастика
        mystery: Детектив
        romance: Романтика

        label:
          fantasy: Магия, мифические существа, вымышленные миры
          scifi: Будущее, технологии, космические путешествия
          mystery: Преступления, расследования, саспенс
          romance: Любовные истории, отношения, эмоции
    features:
      prompt: Выберите элементы книги
      option:
        glossary: Глоссарий
        illustrations: Иллюстрации
        index: Индекс
        bibliography: Библиография

        label:
          glossary: Термины и определения
          illustrations: Изображения и диаграммы
          index: Ключевые слова
          bibliography: Ссылки и источники
    use-typst:
      prompt: Использовать Typst для вёрстки
    use-python:
      prompt: Использовать Python зависимости?
    use-npm:
      prompt: Использовать npm зависимости?
    open-in-code:
      prompt: Открыть проект в VS Code?
    output-format:
      prompt: Формат вывода
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
