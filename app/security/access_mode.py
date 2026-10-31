"""Temporary product-wide access switch; existing security remains available."""
import os


def open_access():
    return os.environ.get('PROJECT2_AUTH_ENABLED','0') != '1'
