# -*- coding: utf-8 -*-
import logging
from odoo import http
from odoo.service.db import list_dbs

_logger = logging.getLogger(__name__)

if not getattr(http.Request, '_easy_sign_patched', False):
    _orig_get_session_and_dbname = http.Request._get_session_and_dbname

    def _patched_get_session_and_dbname(self):
        session, dbname = _orig_get_session_and_dbname(self)
        if dbname:
            try:
                dbs = list_dbs(force=True)
                if dbs and dbname not in dbs:
                    target_db = 'sign' if 'sign' in dbs else dbs[0]
                    _logger.warning("Database %r in session does not exist. Falling back to %r.", dbname, target_db)
                    session.logout(keep_db=False)
                    session.db = target_db
                    dbname = target_db
            except Exception as e:
                _logger.debug("Error verifying database list: %s", e)
        return session, dbname

    http.Request._get_session_and_dbname = _patched_get_session_and_dbname
    http.Request._easy_sign_patched = True

from . import models
from . import controllers
from . import wizard
