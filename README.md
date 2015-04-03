# Tagg-Python Utility/Library

> Tagg is a library and command line utility built to help you manipulate the data of [Tag-Github]

## Installation

```bash
> pip install tagg-python
```

## Usage

`tagg` and `autotagg` should run in the root of the data dir. If you wish to run them outside the data dir, use `-d datadir` to specify the data dir or `--force` to operate in a new data dir.

### Tagg Utility

Tagg cli tool provides basic functionalities to add, remove, update and validate tag and repo data.

#### General

```bash
# Export data to json
tagg export > data.json

# Enter REPL with history, autocomplete and basic syntax highlighting support
tagg shell
```

#### Tags

```bash
# List all tags
tagg tags [list]

# Add a tag named c++ in language domain
tagg tags add language/c++

# Remove a tag and all its links in repos
tagg tags remove language/c++

# Show tag information
tagg tags show language/c++

# Rename a tag and all its links in repos  
tagg tags rename language/c++ language/cplusplus

# Edit tag meta in VIM
tagg tags edit language/c++

# Validate tag data
tagg tags validate
```

#### Repos

```bash
# List all repos
tagg repos [list]

# Find all repos with one or more tags
tagg repos links python,framework

# Find all repos with one or more keywords in their names or descriptions
tagg repos find django

# Add a repo and fetch its meta from Github
tagg repos add django/django

# Remove a repo
tagg repos remove django/django

# Show repo information
tagg repos show django/django

# Edit repo meta in VIM
tagg repos edit django/django

# Rename a repo
tagg repos rename django/django django/django2

# Tag a repo with one or more tags
tagg repos tag django/django language/c++

# Untag a repo
tagg repos untag django/django [language/]c++

# Get stats info of tagged repos
tagg repos link_stats

# Validate repo data
tagg repos validate
```

### Autotagg Utility

Automatically tag repos according to their meta data. By default, it prints a list of suggested commands instead of actually modifying the data.

```bash
# Run on a repo
autotagg owner/name

# Run on all existing repos
autotagg -a|--all

# Get my repos from Github and run on them
autotagg -g GITHUB_ACCOUNT

# Get my repos and also my starred repos from Github and run on them
autotagg -g GITHUB_ACCOUNT --starred

# Get top1k repos from Github and run on them
autotagg --top1k
```

Then to apply commands printed by `autotagg`, just pipe it to `tagg`

```bash
autotag -a > pending_review.txt
cat pending_review.txt | tagg
```

For more details option list please see --help of autotagg

##### Autotagg Definition File

A json file that defines autotag criterias. Let's explain it with an example:

```json
{
    "default_type": "general",
    "brands": {
        "twitter": [
            "twbs", 
            "twitter"
        ]
    },
    "keywords":{
        "framework": [
            "/^django$/"
        ],
        "python": [
            "python",
            "/^py/"
        ]
    }
}
```

This defines three tags:

* "brands/twitter" tag to be placed when the repo owner is "twbs" or "twitter"
* "general/framework" tag to be placed when the repo name is exactly "django"
* "general/python" tag to be placed when the repo name starts with "py" or the keyword "python" shows up anywhere in the repo name or the repo description

# License

MIT

[Tag-Github]: https://github.com/porter-io/tag-github
