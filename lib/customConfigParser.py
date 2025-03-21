"""Custom configparser."""

import configparser
import sys
from io import TextIOWrapper
from typing import cast

if __name__ == "__main__":
    sys.exit(1)


class customConfigParser(configparser.RawConfigParser):
    """Our custom configparser will not remove comments when the file is written.
    Also, it does not raise errors if duplicate options are detected.
    """

    def __init__(self) -> None:
        super().__init__(allow_no_value=True, delimiters=("=",), comment_prefixes=(), strict=False)
        # comment_prefixes=() is necessary to preserve comments.

    def _read(self, fp: TextIOWrapper, fpname: str) -> None:
        """Parse a sectioned configuration file.

        Each section in a configuration file contains a header, indicated by
        a name in square brackets (`[]`), plus key/value options, indicated by
        `name` and `value` delimited with a specific substring (`=` or `:` by
        default).

        Values can span multiple lines, as long as they are indented deeper
        than the first line of the value. Depending on the parser's mode, blank
        lines may be treated as parts of multiline values or ignored.

        Configuration files may include comments, prefixed by specific
        characters (`#` and `;` by default). Comments may appear on their own
        in an otherwise empty line or may be entered in lines holding values or
        section names.
        """

        # This read function was modified to pick the first option value if there is a
        # duplicate option. Any subsequent duplicate option values are discarded.
        elements_added: set[str | tuple[str, str]] = set()
        cursect: dict[str, list[str | int] | None] | None = None
        sectname: str | None = None
        optname = None
        indent_level = 0
        e: configparser.Error | None = None
        for lineno, line in enumerate(fp, start=1):
            comment_start: int | None = sys.maxsize
            # Strip inline comments
            inline_prefixes = dict.fromkeys(self._inline_comment_prefixes, -1)
            while comment_start == sys.maxsize and inline_prefixes:
                next_prefixes = {}
                for prefix, index in inline_prefixes.items():
                    line_index = line.find(prefix, index + 1)
                    if line_index == -1:
                        continue
                    next_prefixes[prefix] = line_index
                    if line_index == 0 or (line_index > 0 and line[line_index - 1].isspace()):
                        comment_start = min(comment_start, line_index)
                inline_prefixes = next_prefixes
            # Strip full line comments
            for prefix in self._comment_prefixes:
                if line.strip().startswith(prefix):
                    comment_start = 0
                    break
            if comment_start == sys.maxsize:
                comment_start = None
            value = line[:comment_start].strip()
            if not value:
                if self._empty_lines_in_values:
                    # Add empty line to the value, but only if there was no comment on the line
                    if comment_start is None and cursect is not None and optname and cursect[optname] is not None:
                        cast("list[str | int]", cursect[optname]).append("")  # newlines added at join
                else:
                    # Empty line marks end of value
                    indent_level = sys.maxsize
                continue
            # Continuation line?
            first_nonspace = self.NONSPACECRE.search(line)
            cur_indent_level = first_nonspace.start() if first_nonspace else 0
            if cursect is not None and optname and cur_indent_level > indent_level:
                cast("list[str | int]", cursect[optname]).append(value)
            # A section header or option header?
            else:
                indent_level = cur_indent_level
                # Is it a section header?
                mo = self.SECTCRE.match(value)
                if mo:
                    sectname = cast("str", mo.group("header"))
                    if sectname in self._sections:
                        if self._strict and sectname in elements_added:
                            raise configparser.DuplicateSectionError(sectname, fpname, lineno)
                        cursect = self._sections[sectname]
                        elements_added.add(sectname)
                    elif sectname == self.default_section:
                        cursect = self._defaults
                    else:
                        cursect = self._dict()
                        self._sections[sectname] = cursect
                        self._proxies[sectname] = configparser.SectionProxy(self, sectname)
                        elements_added.add(sectname)
                    # So sections can't start with a continuation line
                    optname = None
                # No section header in the file?
                elif cursect is None:
                    # Typically you raise a MissingSectionHeaderError when the input file is missing a section hearder
                    # But given the fact that users could have corrupt one with invalid settings, add a dummy TotallyFakeSectionHeader
                    # will fix the problem, and our code later in the pipeline removes invalid sections.
                    cursect = self._dict()
                    sectname = "TotallyFakeSectionHeader"
                    self._sections[sectname] = cursect
                    self._proxies[sectname] = configparser.SectionProxy(self, sectname)
                    elements_added.add(sectname)
                    optname = None

                # An option line?
                else:
                    mo = self._optcre.match(value)
                    if mo:
                        optname, _vi, optval = mo.group("option", "vi", "value")
                        if not optname:
                            e = self._handle_error(e, fpname, lineno, line)
                        optname = self.optionxform(optname.rstrip())
                        sectname = cast("str", sectname)
                        if self._strict and (sectname, optname) in elements_added:
                            raise configparser.DuplicateOptionError(sectname, optname, fpname, lineno)
                        elements_added.add((sectname, optname))
                        # This check is fine because the OPTCRE cannot
                        # match if it would set optval to None.
                        if optval is not None:
                            optval = optval.strip()
                            # Check if this optname already exists
                            if optname not in cursect:
                                cursect[optname] = [optval]
                        elif optname not in cursect:
                            # Valueless option handling
                            cursect[optname] = None
                    else:
                        # A non-fatal parsing error occurred. set up the
                        # exception but keep going. the exception will be
                        # raised at the end of the file and will contain a
                        # list of all bogus lines.
                        e = self._handle_error(e, fpname, lineno, line)

        self._join_multiline_values()  # type: ignore[reportAttributeAccessIssue]
        # If any parsing errors occurred, raise an exception.
        if e:
            raise e
