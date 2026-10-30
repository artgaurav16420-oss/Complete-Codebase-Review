# ADR-006: Write Containment in `ccr.fileio`

## Status

Accepted (unreleased; current release is v2.4.0)

## Context

`ccr` writes agent prompts and reports into a caller-supplied path (`--out`,
`--in`), so the destination is user input, and on a shared machine the cache
directory can be swapped for a symlink between the check and the write.

`ccr/fileio.py` grew a guard for that case across several review rounds without a
written threat model: a maintainer removing `_verify_handle`, the parent-identity
comparison, or the Windows final-path check cannot tell which invariant it
enforces. This ADR records the model so later edits are judged against it rather
than against the commit that added each line.

## Decision

`write_text(path, text, newline="\n", root=None)` enforces, in order:

1. **Root resolution.** When `root` is given it is rejected if it is a symlink,
   then resolved with `realpath`. The destination's `realpath` must share that
   root via `os.path.commonpath`, and its `relpath` must not begin with `..`.
   A caller-supplied root therefore cannot be escaped by spelling alone.
2. **POSIX component walk.** For a rooted write on POSIX, `_open_beneath` opens
   every component from `/` down with `O_NOFOLLOW | O_DIRECTORY` and opens the
   leaf relative to its parent. Because the destination was already passed
   through `realpath`, an intermediate link that resolves *inside* the root is
   followed by the resolution itself; a leaf link is always refused earlier by
   the `os.path.islink(path)` check at the top of `write_text`. The walk's job
   is the race: a link swapped in after the resolution fails the open. A POSIX
   platform without `O_NOFOLLOW` refuses the rooted write outright.
3. **Parent identity (the `_open_checked` path).** On Windows, and for an
   unrooted write, `_open_checked` records the parent directory's
   `(st_dev, st_ino)` before the open and compares it after, and re-checks that
   neither the leaf nor the parent is a symlink. A swap between check and open
   is therefore detected, not written through.
4. **Descriptor identity (`_open_checked` only).** The opened descriptor's
   `fstat` identity is compared with the path's `stat` identity, so the handle
   must name the file the path currently names. The POSIX rooted branch relies
   on the walk instead and does not repeat this comparison.
5. **Windows final path.** Because NTFS reparse points (junctions) are not
   covered by `O_NOFOLLOW` and `os.path.islink` reports False for a junction,
   Windows relies on `_verify_handle`: the opened handle's final path
   (`_windows_final_path`, via `GetFinalPathNameByHandle`) must stay inside the
   resolved root. It does not walk each ancestor.
6. **Newline discipline.** Writes go through the opened handle with an explicit
   `newline` so a Windows run does not rewrite every line ending.

A link that would take the write outside the root is refused. A link that stays
inside the root may be followed on POSIX, because `realpath` resolved it before
the containment check; a leaf link is refused on every platform.

Out of threat model: a hostile process running as the same user, a filesystem
that lies about `stat`, and a root directory that is itself a symlink chosen by
the caller. Those are caller decisions, not tool defects.

## Consequences

- A destination that resolves outside the root is a hard error with a readable
  message.
- Cost is one `open` per path component on the POSIX rooted walk, and a fixed
  handful of `stat` calls on `_open_checked`. Writes are a handful per run, so
  this is not on a hot path.
- `write_text` is not atomic: it truncates the destination before writing, so an
  encode failure leaves an empty file. A temp-file-plus-`os.replace` scheme
  would fix that but changes the containment story (`os.replace` is not
  filtered by the walk), so it is tracked as its own change rather than folded
  in here.
- `tools/generate.py` calls `write_text` without `root` because it writes into
  the checkout it is run from; that is the intended exception.
- `ccr` only reads the baseline. The JSON report carries a fresh snapshot built
  by `aggregate`, with the input baseline feeding only the trend text.
