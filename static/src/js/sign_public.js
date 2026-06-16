/**
 * Easy Sign — Public Signing Page JavaScript
 * Self-hosted electronic signature for Odoo 18
 * Handles: canvas drawing, mouse events, touch events, sign/decline submission
 */
(function () {
    'use strict';


    document.addEventListener('DOMContentLoaded', function () {

        /* ---- Element references ---- */
        var canvas          = document.getElementById('signatureCanvas');
        var canvasWrap      = canvas && canvas.parentElement;
        var canvasHint      = document.querySelector('.es-canvas-hint');
        var canvasStatus    = document.getElementById('canvasStatus');
        var btnClear        = document.getElementById('btnClear');
        var btnSign         = document.getElementById('btnSign');
        var btnSignText     = document.getElementById('btnSignText');
        var btnSignSpinner  = document.getElementById('btnSignSpinner');
        var btnShowDecline  = document.getElementById('btnShowDecline');
        var declineForm     = document.getElementById('declineForm');
        var declineReason   = document.getElementById('declineReason');
        var btnCancelDecline   = document.getElementById('btnCancelDecline');
        var btnConfirmDecline  = document.getElementById('btnConfirmDecline');
        var msgSuccess      = document.getElementById('msgSuccess');
        var msgError        = document.getElementById('msgError');
        var msgErrorText    = document.getElementById('msgErrorText');
        var msgDeclined     = document.getElementById('msgDeclined');

        if (!canvas) {
            return;
        }

        /* ---- Canvas context setup ---- */
        var ctx = canvas.getContext('2d');
        var isDrawing   = false;
        var hasSigned   = false;
        var lastX       = 0;
        var lastY       = 0;

        function initCanvas() {
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.strokeStyle = '#1a1a2e';
            ctx.lineWidth   = 2.5;
            ctx.lineCap     = 'round';
            ctx.lineJoin    = 'round';
        }

        initCanvas();


        function getCanvasCoords(event) {
            var rect = canvas.getBoundingClientRect();
            var scaleX = canvas.width  / rect.width;
            var scaleY = canvas.height / rect.height;
            var clientX, clientY;
            if (event.touches && event.touches.length > 0) {
                clientX = event.touches[0].clientX;
                clientY = event.touches[0].clientY;
            } else {
                clientX = event.clientX;
                clientY = event.clientY;
            }
            return {
                x: (clientX - rect.left) * scaleX,
                y: (clientY - rect.top)  * scaleY,
            };
        }

        function startDraw(x, y) {
            isDrawing = true;
            lastX = x;
            lastY = y;
            ctx.beginPath();
            ctx.moveTo(x, y);
            if (canvasWrap) {
                canvasWrap.classList.add('es-canvas-active');
            }
        }

        function draw(x, y) {
            if (!isDrawing) { return; }
            ctx.lineTo(x, y);
            ctx.stroke();
            lastX = x;
            lastY = y;
            if (!hasSigned) {
                hasSigned = true;
                if (canvasHint) { canvasHint.classList.add('hidden'); }
                if (canvasStatus) { canvasStatus.textContent = 'Signature captured'; }
            }
        }

        function endDraw() {
            isDrawing = false;
            ctx.closePath();
            if (canvasWrap) {
                canvasWrap.classList.remove('es-canvas-active');
            }
        }


        canvas.addEventListener('mousedown', function (e) {
            e.preventDefault();
            var coords = getCanvasCoords(e);
            startDraw(coords.x, coords.y);
        });

        canvas.addEventListener('mousemove', function (e) {
            e.preventDefault();
            if (!isDrawing) { return; }
            var coords = getCanvasCoords(e);
            draw(coords.x, coords.y);
        });

        canvas.addEventListener('mouseup', function (e) {
            e.preventDefault();
            endDraw();
        });

        canvas.addEventListener('mouseleave', function (e) {
            if (isDrawing) { endDraw(); }
        });


        canvas.addEventListener('touchstart', function (e) {
            e.preventDefault();
            var coords = getCanvasCoords(e);
            startDraw(coords.x, coords.y);
        }, { passive: false });

        canvas.addEventListener('touchmove', function (e) {
            e.preventDefault();
            var coords = getCanvasCoords(e);
            draw(coords.x, coords.y);
        }, { passive: false });

        canvas.addEventListener('touchend', function (e) {
            e.preventDefault();
            endDraw();
        }, { passive: false });

        canvas.addEventListener('touchcancel', function (e) {
            endDraw();
        });


        if (btnClear) {
            btnClear.addEventListener('click', function () {
                initCanvas();
                hasSigned = false;
                if (canvasHint)   { canvasHint.classList.remove('hidden'); }
                if (canvasStatus) { canvasStatus.textContent = ''; }
                hideMessages();
            });
        }


        function hideMessages() {
            if (msgSuccess) { msgSuccess.classList.add('d-none'); }
            if (msgError)   { msgError.classList.add('d-none'); }
            if (msgDeclined){ msgDeclined.classList.add('d-none'); }
        }

        function showError(text) {
            hideMessages();
            if (msgError && msgErrorText) {
                msgErrorText.textContent = text;
                msgError.classList.remove('d-none');
            }
        }

        function setSignButtonLoading(loading) {
            if (!btnSign) { return; }
            btnSign.disabled = loading;
            if (btnSignText)    { btnSignText.classList.toggle('d-none', loading); }
            if (btnSignSpinner) { btnSignSpinner.classList.toggle('d-none', !loading); }
        }


        if (btnSign) {
            btnSign.addEventListener('click', function () {
                if (!hasSigned) {
                    showError('Please draw your signature in the box before submitting.');
                    if (canvasWrap) {
                        canvasWrap.style.borderColor = '#e74c3c';
                        setTimeout(function () {
                            canvasWrap.style.borderColor = '';
                        }, 2000);
                    }
                    return;
                }

                var token = btnSign.getAttribute('data-token');
                if (!token) {
                    showError('Missing token. Please reload the page.');
                    return;
                }

                var signatureDataURL = canvas.toDataURL('image/png');

                setSignButtonLoading(true);
                hideMessages();

                var formData = new FormData();
                formData.append('signature', signatureDataURL);

                fetch('/sign/submit/' + token, {
                    method: 'POST',
                    body: formData,
                })
                .then(function (response) {
                    return response.json().then(function (data) {
                        return { status: response.status, data: data };
                    });
                })
                .then(function (result) {
                    setSignButtonLoading(false);
                    if (result.data && result.data.success) {
                        // Success — show message and disable further interaction
                        if (msgSuccess) { msgSuccess.classList.remove('d-none'); }
                        if (btnSign)    { btnSign.style.display = 'none'; }
                        if (btnClear)   { btnClear.disabled = true; }
                        if (btnShowDecline) { btnShowDecline.style.display = 'none'; }
                        if (canvasWrap) { canvasWrap.style.pointerEvents = 'none'; }
                        if (canvasStatus) { canvasStatus.textContent = ''; }
                        // Redirect to success page after 2 seconds
                        setTimeout(function () {
                            window.location.href = '/sign/view/' + token;
                        }, 2000);
                    } else {
                        showError(
                            (result.data && result.data.error)
                                ? result.data.error
                                : 'An unexpected error occurred. Please try again.'
                        );
                    }
                })
                .catch(function (err) {
                    setSignButtonLoading(false);
                    showError('Network error: ' + err.message + '. Please check your connection and try again.');
                });
            });
        }


        if (btnShowDecline) {
            btnShowDecline.addEventListener('click', function () {
                if (declineForm) { declineForm.classList.remove('d-none'); }
                btnShowDecline.style.display = 'none';
                hideMessages();
            });
        }

        if (btnCancelDecline) {
            btnCancelDecline.addEventListener('click', function () {
                if (declineForm) { declineForm.classList.add('d-none'); }
                if (btnShowDecline) { btnShowDecline.style.display = ''; }
            });
        }

        if (btnConfirmDecline) {
            btnConfirmDecline.addEventListener('click', function () {
                var token  = btnConfirmDecline.getAttribute('data-token');
                var reason = declineReason ? declineReason.value.trim() : '';

                if (!token) {
                    showError('Missing token. Please reload the page.');
                    return;
                }

                btnConfirmDecline.disabled = true;
                btnConfirmDecline.textContent = 'Declining…';
                hideMessages();

                var formData = new FormData();
                formData.append('reason', reason);

                fetch('/sign/decline/' + token, {
                    method: 'POST',
                    body: formData,
                })
                .then(function (response) {
                    return response.json().then(function (data) {
                        return { status: response.status, data: data };
                    });
                })
                .then(function (result) {
                    btnConfirmDecline.disabled = false;
                    btnConfirmDecline.textContent = 'Confirm Decline';

                    if (result.data && result.data.success) {
                        if (declineForm) { declineForm.classList.add('d-none'); }
                        if (msgDeclined) { msgDeclined.classList.remove('d-none'); }
                        if (btnSign)     { btnSign.style.display = 'none'; }
                        if (canvasWrap)  { canvasWrap.style.pointerEvents = 'none'; }
                        // Redirect to declined page
                        setTimeout(function () {
                            window.location.href = '/sign/view/' + token;
                        }, 2000);
                    } else {
                        showError(
                            (result.data && result.data.error)
                                ? result.data.error
                                : 'Failed to decline. Please try again.'
                        );
                        btnConfirmDecline.disabled = false;
                    }
                })
                .catch(function (err) {
                    btnConfirmDecline.disabled = false;
                    btnConfirmDecline.textContent = 'Confirm Decline';
                    showError('Network error: ' + err.message);
                });
            });
        }

    });

})();
