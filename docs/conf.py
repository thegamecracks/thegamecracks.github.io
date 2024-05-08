# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "thegamecracks"
copyright = "2024, thegamecracks"
author = "thegamecracks"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "ablog",
    "sphinx.ext.intersphinx",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", ".gitkeep"]

# Configuration for ablog
# https://ablog.readthedocs.io/en/stable/
blog_baseurl = "https://thegamecracks.github.io/"
blog_post_pattern = "posts/*.rst"
post_date_format = "%Y %B %d"
post_date_format_short = "%B %Y"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_title = "thegamecracks"
html_theme = "sphinx_book_theme"
html_static_path = ["_static"]
html_theme_options = {
    "repository_url": "https://github.com/thegamecracks/thegamecracks.github.io",
    "repository_branch": "master",
    "use_repository_button": True,
    "use_download_button": False,
}
html_sidebars = {
    "blog/*": [
        "navbar-logo.html",
        "search-field.html",
        "ablog/postcard.html",
        "ablog/recentposts.html",
        "ablog/tagcloud.html",
        "ablog/categories.html",
        "ablog/archives.html",
        "sbt-sidebar-nav.html",
    ],
    "posts/*": [
        "navbar-logo.html",
        "search-field.html",
        "ablog/postcard.html",
        "ablog/recentposts.html",
        # "ablog/tagcloud.html",
        # "ablog/categories.html",
        # "ablog/archives.html",
        "sbt-sidebar-nav.html",
    ],
    "index": [
        "navbar-logo.html",
        "search-field.html",
        # "ablog/postcard.html",
        # "ablog/recentposts.html",
        # "ablog/tagcloud.html",
        # "ablog/categories.html",
        "ablog/archives.html",
        "sbt-sidebar-nav.html",
    ],
}
