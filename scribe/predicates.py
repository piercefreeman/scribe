from collections.abc import Callable

from rich.console import Console

from scribe.context import PageContext, PageStatus

console = Console()


class PredicateMatcher:
    predicate_functions: dict[str, Callable[[PageContext], bool]]

    def __init__(self):
        self.predicate_functions = {
            "all": lambda ctx: True,
            "has_tag": lambda tag: lambda ctx: tag in (ctx.tags or []),
            "is_published": lambda ctx: ctx.status == PageStatus.PUBLISH,
            "is_draft": lambda ctx: ctx.status == PageStatus.DRAFT,
            "is_scratch": lambda ctx: ctx.status == PageStatus.SCRATCH,
            "is_note": lambda ctx: getattr(ctx.frontmatter, "type", None) == "note"
            if ctx.frontmatter
            else False,
            "is_blog": lambda ctx: getattr(ctx.frontmatter, "type", None) == "blog"
            if ctx.frontmatter
            else False,
        }

    def matches_predicates(self, ctx: PageContext, predicates: tuple[str, ...]) -> bool:
        """Check if a note context matches all given predicates."""
        for predicate_name in predicates:
            # Check for negation prefix
            negated = predicate_name.startswith("!")
            actual_predicate = predicate_name[1:] if negated else predicate_name

            # Handle parameterized predicates with colon syntax
            # (e.g., "predicate_name:parameter")
            if ":" in actual_predicate:
                base_predicate, parameter = actual_predicate.split(":", 1)
                if base_predicate in self.predicate_functions:
                    predicate_factory = self.predicate_functions[base_predicate]
                    try:
                        # Try to call the factory function with the parameter
                        predicate_func = predicate_factory(parameter)
                        result = predicate_func(ctx)
                    except (TypeError, AttributeError):
                        # If the predicate is not a factory function, treat as unknown
                        console.print(
                            f"[yellow]Warning: Predicate '{base_predicate}' "
                            f"does not accept parameters[/yellow]"
                        )
                        return False
                else:
                    # Unknown base predicate
                    console.print(
                        f"[yellow]Warning: Unknown predicate "
                        f"'{base_predicate}'[/yellow]"
                    )
                    return False
            elif actual_predicate in self.predicate_functions:
                predicate_func = self.predicate_functions[actual_predicate]
                result = predicate_func(ctx)
            else:
                # Unknown predicate - treat as False
                console.print(
                    f"[yellow]Warning: Unknown predicate '{actual_predicate}'[/yellow]"
                )
                return False

            # Apply negation if needed
            if negated:
                result = not result

            if not result:
                return False

        return True
