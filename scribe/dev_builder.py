"""Development-specific builder that injects live reload functionality."""

from scribe.builder import SiteBuilder
from scribe.context import PageContext


class DevSiteBuilder(SiteBuilder):
    """Development builder that injects live reload script into HTML pages."""

    def _generate_html(self, ctx: PageContext) -> str:
        """Generate HTML for a page context with live reload script."""
        # Get base HTML from parent
        html_content = super()._generate_html(ctx)

        # Inject live reload script before closing head tag
        reload_script = """
<script>
(function() {
    console.log('🔄 Live reload enabled');

    function connectToReloadServer() {
        const eventSource = new EventSource('/_dev/reload');

        eventSource.onmessage = function(event) {
            if (event.data === 'reload') {
                console.log('🔄 Reloading page...');
                window.location.reload();
            } else if (event.data === 'disconnect') {
                console.log('🔌 Server shutting down, closing connection');
                eventSource.close();
                return; // Don't reconnect
            } else if (event.data === 'connected') {
                console.log('✅ Live reload connected');
            }
        };

        eventSource.onerror = function(event) {
            console.log('⚠️ Live reload connection lost, retrying...');
            eventSource.close();
            setTimeout(connectToReloadServer, 1000);
        };
    }

    // Start connection when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', connectToReloadServer);
    } else {
        connectToReloadServer();
    }
})();
</script>
"""

        # Inject before closing head tag, or before closing html tag if no head
        if "</head>" in html_content:
            html_content = html_content.replace("</head>", f"{reload_script}</head>")
        elif "</html>" in html_content:
            html_content = html_content.replace("</html>", f"{reload_script}</html>")
        else:
            # If no proper HTML structure, append script
            html_content += reload_script

        return html_content
