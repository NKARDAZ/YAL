# YAL

**YAL** is a command-line utility for project initialization and updates based on templates.

## Commands

- `yal create <kind>[:<name>][@<ref>]` — uses a template to create a new project (currently supports only `book` kind)
- `yal update <kind>[:<name>]` — updates an existing project (currently supports only `book` kind)
- `yal add <kind>:<name> from <repository URL>` — registers an external template from GitHub with the specified name

## Create a project
Downloads the template (if not cached locally) and initiates the configuration process.
```bash
# Basic usage
yal create book

# Using a specific template
yal create book:template-name

# Using a specific version (tag or commit hash)
yal create book@version

# Combined usage
yal create book:template-name@version
```
## yal.toml

A configuration file used in the root of the created project. It contains information about the used template and allows you to create local commands for the project. The `yal.toml` file is located in the root of the project and may have a structure like the following:

```toml
[origin]
template = "book"
template-version = "9670322" # commit hash if created from commit version of template
created-at = "2026-05-31T03:16:33Z"
yal-version = "0.1.1"

[[command]]
name = "make"
arguments = {--mode = []} # [] allows any value
script = "/build/build.py"
exec = "python3"
# yal make → python3 build/build.py
# yal make --mode=print → python3 build/build.py --mode=print

[[command]]
name = "make print"
macros = "make --mode=print"
# yal make print → yal make --mode=print → python3 build/build.py --mode=print
```

If `yal.toml` not present in the template, it will be created automatically with default `[origin]` section.


## yal.template.toml

A configuration file used as a prompt when creating a project from a template. The `yal.template.toml` file is located in the root of the template and may have a structure like the following:

```toml
[meta]
yal-min-version = "0.1.1"

[[fields]]
id             = "book-name"
type           = "text"
required       = true
default        = "{placeholder}"
is-folder-name = true

[[fields]]
id       = "book-author"
type     = "text"
required = false
default  = ""

[[fields]]
id       = "book-lang"
type     = "select"
required = true
default  = "en-US"

[[fields]]
id       = "book-genre"
type     = "text"
required = false
default  = ""

[messages.ru]
book-name.prompt      = "Введите название книги"
book-name.placeholder = "Книга без названия"
book-author.prompt    = "Введите имя автора"
book-author.placeholder = "Аноним"
book-lang.prompt      = "Выберите локализацию книги в формате ISO-639, ISO-3166"
book-genre.prompt     = "Введите жанр книги"

[messages.en]
book-name.prompt      = "Enter book title"
book-name.placeholder = "Untitled book"
book-author.prompt    = "Enter author name"
book-author.placeholder = "Anonymous"
book-lang.prompt      = "Select book locale  in ISO-639, ISO-3166 format"
book-genre.prompt     = "Enter book genre"

[[targets]]
file   = "/meta/book.yml"
format = "yaml"

[[targets.fields]]
value = "${UUID}" # ${} syntax calls built-in generator: UUID, DATE, TIMESTAMP, RANDOM
key   = "book.uuid"

[[targets.fields]]
field = "book-name"
key   = "book.title"

[[targets.fields]]
field = "book-author"
key   = "author[0].name"

[[targets.fields]]
field = "book-lang"
key   = "property.locale"

[[targets.fields]]
field = "book-genre"
key   = "property.genre"

```


## Built-in templates


### \<Book\> Typst Book Template 

- **Repo:** https://github.com/DemerNkardaz/Typst-Book-Template
- **Name:** default
- **Use:** `yal create book`

A template for creating a book using [Typst](https://typst.app/), including a prebuilt structure, plugins, styles, settings, and a build system that combines Typst and Python tools.

Requires installation of the [Typst compiler](https://github.com/typst/typst/releases) and the Python packages `pyyaml`, `pikepdf`, and `pillow`.
```bash
pip install pyyaml pikepdf pillow
```
