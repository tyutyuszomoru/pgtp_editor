from PySide6.QtWidgets import QMessageBox

ABOUT_TEXT = (
    "<h3>PGTP Editor</h3>"
    "<p>A companion editor for SQL Maestro PostgreSQL PHP Generator "
    "<code>.pgtp</code> project files. Licensed under GPL-3.0.</p>"
    "<p><b>Credits:</b></p>"
    "<ul>"
    "<li><a href=\"https://github.com/driscollis/BoomslangXML\">BoomslangXML</a> "
    "(Mike Driscoll) &mdash; prior art for the tree-based XML editing approach.</li>"
    "<li><a href=\"https://github.com/luchko/QCodeEditor\">QCodeEditor</a> "
    "(luchko, MIT License) &mdash; the code-editor widget is a PySide6 port "
    "of this project's approach.</li>"
    "<li><a href=\"https://github.com/LcfherShell/SuperNano\">SuperNano</a> "
    "(LcfherShell, GPL-3.0) &mdash; evaluated during design; not used as a "
    "runtime dependency.</li>"
    "</ul>"
)


def show_about_dialog(parent):
    QMessageBox.about(parent, "About PGTP Editor", ABOUT_TEXT)
