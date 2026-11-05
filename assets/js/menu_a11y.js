
    <script>
    (function () {
      try {
        var doc = window.parent.document;
        function patchMenuButton() {
          var btn = doc.querySelector('.st-key-top_settings_popover button');
          if (!btn) return;
          if (btn.getAttribute('type') !== 'button') btn.setAttribute('type', 'button');
          var expanded = btn.getAttribute('aria-expanded') === 'true';
          var label = expanded ? 'Close menu' : 'Open menu';
          if (btn.getAttribute('aria-label') !== label) btn.setAttribute('aria-label', label);
          var body = expanded ? doc.querySelector('div[data-testid="stPopoverBody"][aria-label="Menu"]') : null;
          if (body) {
            if (!body.id) body.id = 'jobscout-account-menu';
            if (btn.getAttribute('aria-controls') !== body.id) btn.setAttribute('aria-controls', body.id);
          } else if (btn.hasAttribute('aria-controls')) {
            btn.removeAttribute('aria-controls');
          }
        }
        if (window.parent.__jobscoutMenuA11y) {
          window.parent.__jobscoutMenuA11y();
          return;
        }
        window.parent.__jobscoutMenuA11y = patchMenuButton;
        patchMenuButton();
        new MutationObserver(patchMenuButton).observe(doc.body, {
          childList: true,
          subtree: true,
          attributes: true,
          attributeFilter: ['aria-expanded']
        });
      } catch (e) {}
    })();
    </script>
    