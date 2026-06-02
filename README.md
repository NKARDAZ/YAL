# [YAL](https://pypi.org/project/yal-cmd/)

**YAL** is a command-line utility for project initialization and updates based on templates from git repositories.

It also supports project-local commands (similar to Makefile targets or scripts in package.json). Define them in `yal.toml` and invoke them with `yal <command>`.

## Commands

- `yal new <kind>[:<name>][@<ref>]` — uses a template to create a new project; if name is not specified, the `default` template will be used
- `yal update <kind>[:<name>]` — downloads and caches the latest version of a template
- `yal add <kind>:<name>[@<ref>] from <repository URL | user/repo>` — registers an external template from GitHub with the specified name
- `yal remove <kind>[:<name>[@<version>]]` — removes a template from the local storage; if name is not specified, all templates of the given kind will be removed

---

## Create a project

Downloads the template (if not cached locally) and initiates the configuration process.

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
```

If the requested version is already cached locally, YAL skips the download. If no version is specified, YAL uses the most recent locally cached version; if none is cached, it downloads the latest release (or the latest commit if the repository has no releases).

---

## Update a template

Downloads and caches the latest version of a template without creating a project. Useful for pre-caching before working offline.

```bash
yal update book
yal update book:my-theme
```

---

## Add an external template

Registers a GitHub repository as a named template under a given kind, then downloads it.

```bash
# Register and download the latest release (or commit)
yal add book:my-theme from https://github.com/user/my-book-template
# shortcut for GitHub
yal add book:my-theme from user/my-book-template
# or
yal add book:my-theme <other git service/local repo>

# Register a specific version
yal add book:my-theme@1.2.0 from user/my-book-template
```

After registration the template is available like any built-in one:

```bash
yal new book:my-theme
yal update book:my-theme
```

Registered templates are stored in `~/.yal/user-templates.toml`. Downloaded files go to `~/.yal/user-templates/<kind>/<name>/<version>/`.


## Git

You can use any Git hosting service or a local repository. Built-in shortcuts are available for a number of services:

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

Removes cached template files from local storage. When all versions of a user-registered template are removed, its registry entry is also deleted.

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

A configuration file placed in the root of the created project. It stores metadata about the template used and lets you define local commands for the project.

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

If `yal.toml` is not present in the template, it will be created automatically with a default `[origin]` section filled in on project creation.

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

A configuration file placed in the root of a template repository. When present, YAL uses it to interactively prompt the user for values during `yal create`, then applies them to target files in the new project.

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
type    = "text"
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

| Field            | Description                                                                                                  |
| ---------------- | ------------------------------------------------------------------------------------------------------------ |
| `id`             | Unique identifier, used as key in mappings and message lookups                                               |
| `type`           | Input type; currently `text`                                                                                 |
| `required`       | If `true`, the user must provide a non-empty value                                                           |
| `default`        | Default value used if the user presses Enter without typing. Use `"{placeholder}"` to mirror the placeholder |
| `options`        | If non-empty, restricts accepted values to this list                                                         |
| `is-folder-name` | If `true`, the field's value becomes the name of the created project folder                                  |

### Targets

After collecting field values, YAL writes them into files specified under `[[targets]]`:

```toml
[[targets]]
file   = "/config/meta.yaml"
format = "yaml"

  [[targets.fields]]
  key   = "project.name"          # dot-separated YAML path
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
```

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

Field values can be interpolated with `{field-id}` syntax and combined freely with generators: `"© {author}, ${YEAR}"`.

### Localization

Messages support per-language overrides. YAL detects the system locale automatically and falls back to the base (top-level) messages if no translation is found for the current language.

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

A template for creating a book using [Typst](https://typst.app/), including a prebuilt structure, plugins, styles, settings, and a build system combining Typst and Python tools.

**Requirements:** [Typst compiler](https://github.com/typst/typst/releases) and the following Python packages:

```bash
pip install pyyaml pikepdf pillow
```

---

## Custom templates

Any public repository can be registered as a template. The repository does not need to contain a `yal.template.toml` — YAL will copy it as-is and create a default `yal.toml` in the resulting project.

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
yal-min-version = "0.1.1"
post-commands   = ["git init", "npm install"]

[[fields]]
id             = "project-name"
type           = "text"
required       = true
is-folder-name = true

[[fields]]
id      = "author"
type    = "text"
default = "{placeholder}"

[[targets]]
file   = "/package.json"
format = "json"

  [[targets.fields]]
  key   = "name"
  field = "project-name"

  [[targets.fields]]
  key   = "author"
  field = "author"

[messages]
project-name.prompt      = "Project name"
author.prompt            = "Author"
author.placeholder       = "Your Name"
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

`yal-meta.json` stores the kind, name, version, source type (`release` or `commit`), repository URL, release date, and install date for each cached template.

---

## Authentication

YAL supports using personal access tokens to access private repositories and to reduce API rate limits.

- For provider HTTP APIs, YAL recognizes these environment variables:
  - `GITHUB_TOKEN` or `GH_TOKEN` — GitHub API
  - `GITLAB_TOKEN` or `GL_TOKEN` — GitLab API
  - `CODEBERG_TOKEN` or `FORGEJO_TOKEN` — Codeberg / Forgejo API

- For Git operations (`git ls-remote`, `git clone`) YAL will, when a token is available for the host, inject it into HTTPS URLs as a practical fallback. Supported variables for HTTPS auth include:
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

Note: token injection into URLs is only performed for HTTPS remotes and only when the corresponding environment variable is set. SSH remotes (`git@...`) are left unchanged and use SSH keys.
