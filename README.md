# YAL

**YAL** is a command-line utility for project initialization and updates based on templates.

## Commands

- `yal create <kind>[:<name>][@<ref>]` — uses a template to create a new project (currently supports only `book` kind)
- `yal update <kind>[:<name>]` — updates an existing project (currently supports only `book` kind)

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

A configuration file used as a prompt when creating a project from a template. The `yal.toml` file is located in the root of the template and may have a structure like the following:

```toml
[meta]
yal-min-version = "0.1.0"

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
options  = ["ru", "en", "de"]
default  = "ru"

[messages.ru]
book-name.prompt      = "Введите название книги"
book-name.placeholder = "Книга без названия"
book-author.prompt    = "Введите имя автора"
book-author.placeholder = "Аноним"
book-lang.prompt      = "Выберите язык книги в формате ISO-639"

[messages.en]
book-name.prompt      = "Enter book title"
book-name.placeholder = "Untitled book"
book-author.prompt    = "Enter author name"
book-author.placeholder = "Anonymous"
book-lang.prompt      = "Select book language in ISO-639 format"

[[targets]]
file   = "/meta/book.yml"
format = "yaml"

[[targets.fields]]
field = "book-name"
key   = "book.title"

[[targets.fields]]
field = "book-author"
key   = "author[0].name"

[[targets.fields]]
field = "book-lang"
key   = "property.language[ISO-639]"
```


## Built-in templates


### \<Book\> Typst Book Template 

- **Repo:** https://github.com/DemerNkardaz/Typst-Book-Template
- **Name:** default

A template for creating a book using [Typst](https://typst.app/), including a prebuilt structure, plugins, styles, settings, and a build system that combines Typst and Python tools.

Requires installation of the [Typst compiler](https://github.com/typst/typst/releases) and the Python packages `pyyaml`, `pikepdf`, and `pillow`.
```bash
pip install pyyaml pikepdf pillow
```
