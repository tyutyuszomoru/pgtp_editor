# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from PySide6.QtWidgets import QMessageBox

from pgtp_editor.version import __version__ as APP_VERSION

# **Every version number in this box is LABELLED, and that is a requirement, not
# a style choice** (`FQ-260810164455`). Two unrelated versions render here — the
# app's own release and the *vendor's* `.pgtp` project-format version — and they
# were conflated once already, because an app release number two lines above
# `22.8` with neither one saying what it versions invites exactly that. (This
# comment deliberately does not quote the app's current version either — a test
# asserts that no release-shaped literal appears anywhere in this file, and a
# comment is exactly where a stale one would hide.) So the app line says
# "PGTP Editor version", the format line says "`.pgtp` project format version",
# and neither number appears bare.
#
# The app version comes from `pgtp_editor.version`, which reads the single
# literal in `pyproject.toml` — there is no version string spelled out in this
# file, and adding one would defeat the feature.
ABOUT_TEXT = (
    "<h3>PGTP Editor</h3>"
    f"<p><b>PGTP Editor version {APP_VERSION}</b></p>"
    "<p>A companion editor for SQL Maestro PostgreSQL PHP Generator "
    "<code>.pgtp</code> project files.</p>"
    "<p>Copyright &copy; 2026 Botond Zalai-Ruzsics. Licensed under the "
    "GNU General Public License, version 3 (GPL-3.0-only).</p>"
    "<p><b>Authors:</b></p>"
    "<ul>"
    "<li>Botond Zalai-Ruzsics</li>"
    "<li>MDS &mdash; Maintenance Data Services "
    "(<a href=\"https://maint-data.com\">maint-data.com</a>)</li>"
    "</ul>"
    "<p><b>Disclaimer:</b> PGTP Editor and MDS are not affiliated with, "
    "endorsed by, or connected to SQL Maestro Group. The software is provided "
    "\"as is\", without warranty of any kind. The authors accept no liability "
    "for damaged or corrupted <code>.pgtp</code> files &mdash; please keep "
    "backups of your projects.</p>"
    "<p>PGTP Editor targets the PHP Generator "
    "<a href=\"https://www.sqlmaestro.com\">PHP Generator for PostgreSQL</a> "
    "<code>.pgtp</code> <b>project format version 22.8</b> &mdash; SQL Maestro's "
    "format version, not this application's. PHP Generator for "
    "PostgreSQL is a product of SQL Maestro Group.</p>"
    "<p><b>Credits:</b></p>"
    "<ul>"
    "<li><a href=\"https://github.com/driscollis/BoomslangXML\">BoomslangXML</a> "
    "(Mike Driscoll) &mdash; prior art for the tree-based XML editing approach.</li>"
    "<li><a href=\"https://github.com/luchko/QCodeEditor\">QCodeEditor</a> "
    "(luchko, MIT License) &mdash; the code-editor widget is a PySide6 port "
    "of this project's approach.</li>"
    "<li><a href=\"https://github.com/KDE/breeze-icons\">Breeze icons</a> "
    "(KDE, LGPL-3.0) &mdash; the toolbar icons, recolored at runtime.</li>"
    "<li><a href=\"https://github.com/ColinDuquesnoy/QDarkStyleSheet\">"
    "QDarkStyleSheet</a> (Colin Duquesnoy, MIT License) &mdash; the dark "
    "theme's application stylesheet.</li>"
    "</ul>"
)


def show_about_dialog(parent):
    QMessageBox.about(parent, "About PGTP Editor", ABOUT_TEXT)
