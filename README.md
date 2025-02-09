# scribe

Blogging system for my personal site, [freeman.vc](https://freeman.vc). Intended as a bare-bones and fast Python library that supports:

- Filesystem-based markdown notes
- Code & terminal syntax support
- Note lifecycle support; work on drafts concurrently with published notes
- Fast rebuilding of the full website payload
- Tailwind styling support
- Local development server

## Conventions

Raw markdown files are used as the dynamic blog entries of the site. These files drive their own customization - in order to do so we rely on some file conventions.

1. Posts are expected to begin with a header that determines the post title and its URL.
2. Posts include a `meta` yaml body that specify its properties.
3. Images bundled with the post should live within the same folder as the parent post.

```
# Header

meta:
    date: February 2, 2022
    status: publish
    tags:
        - tag1
        - tag2

This post is the next best thing since the Apple I.
```

For full metadata schematic, see the `NoteMetadata` class.

**date**: Human readible date, parsed with the `python-dateutil` parser. This supports fuzzy parsing but I typically use a `Month Day, Year` convention.

**status**:  Articles are scratch drafts by default. This means they won't be published anywhere on the website at build time. Files without the `meta` are also considered scratch notes, so early works in progress won't be bundled. Documents set to `state: draft` will create a page that's only resolvable with its direct link. Draft pages won't be available in the global index that appears on the homepage. Add the `state: publish` metadata flag to consider it launched and therefore globally visible.

**tags**: List of tags that are tied to this page. These can be filtered in the jinja templates using the `filter_tag` function plugin.

**featured_photos**: Data structure to store images that don't appear in the page body but should be used in different elements of the site. Used currently for the travel photo gallary.

## Getting Started

To install:

```bash
uv sync
npm install
```

When writing, use the auto-refresh utility:

```bash
start-writing --notes public [--port]
```

If you'd like to build without the full CLI:

```bash
build-notes --notes public
```

## ZSH Shortcuts

To make it easier to work with scribe, you can add the following to your `~/.zshrc`:

```zsh
# Scribe blog shortcut
scribe() {
    cd ~/projects/scribe && uv run start-writing --notes ~/notes/public "$@"
}
```

After adding this, reload your shell configuration with `source ~/.zshrc`. Then you can simply type:

```zsh
scribe
```

This will:
1. Navigate to your scribe directory
2. Install/update dependencies using uv
3. Start the writing server

You can also pass additional arguments like `--port` directly: `scribe --port 8001`

## Styles

Default styles are generated by Tailwind, which is automatically launched when `start-writing` is invoked. To watch or regenerate the styles explicitly, run:

```
npx tailwindcss -i ./style.css -o ./scribe/resources/style.css --watch
```

Code highlighting is powered by pygmentize with the solarized-dark theme. These styles operate separately from tailwind. To generate, run:

```
pygmentize -S solarized-dark -f html -a .codehilite > ./scribe/resources/code.css
```
