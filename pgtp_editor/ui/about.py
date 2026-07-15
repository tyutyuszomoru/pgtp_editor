from PySide6.QtWidgets import QMessageBox

ABOUT_TEXT = (
    "<h3>PGTP Editor</h3>"
    "<p>A companion editor for SQL Maestro PostgreSQL PHP Generator "
    "<code>.pgtp</code> project files. Licensed under GPL-3.0.</p>"
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
    "<code>.pgtp</code> project format, version 22.8. PHP Generator for "
    "PostgreSQL is a product of SQL Maestro Group.</p>"
    "<p><b>Credits:</b></p>"
    "<ul>"
    "<li><a href=\"https://github.com/driscollis/BoomslangXML\">BoomslangXML</a> "
    "(Mike Driscoll) &mdash; prior art for the tree-based XML editing approach.</li>"
    "<li><a href=\"https://github.com/luchko/QCodeEditor\">QCodeEditor</a> "
    "(luchko, MIT License) &mdash; the code-editor widget is a PySide6 port "
    "of this project's approach.</li>"
    "</ul>"
)


def show_about_dialog(parent):
    QMessageBox.about(parent, "About PGTP Editor", ABOUT_TEXT)
