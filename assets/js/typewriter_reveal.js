
                        <script>
                        (function() {
                            if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
                            var root = document.getElementById('confirm-reveal');
                            if (!root) return;
                            var els = Array.prototype.slice.call(root.querySelectorAll('.tw-text'));
                            var full = els.map(function(el) { return el.textContent; });
                            var total = full.join('').length || 1;
                            var perChar = Math.max(8, Math.min(42, 4200 / total));
                            var li = 0, ci = 0;
                            els.forEach(function(el) { el.textContent = ''; });
                            function step() {
                                if (li >= els.length) return;
                                var el = els[li], txt = full[li], line = el.parentElement;
                                line.classList.add('tw-active');
                                if (ci <= txt.length) { el.textContent = txt.slice(0, ci); ci++; setTimeout(step, perChar); }
                                else { line.classList.remove('tw-active'); li++; ci = 0; setTimeout(step, 200); }
                            }
                            step();
                        })();
                        </script>
                        