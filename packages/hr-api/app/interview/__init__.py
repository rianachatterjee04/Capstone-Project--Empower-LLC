"""The DB-backed interview domain.

Every assessment this package produces can name the words it came from. That
is the whole design constraint: `app/interview/models.py` gives evidence a real
foreign key to a transcript segment and a recording offset, so a recruiter can
click a score and land on the moment the candidate said the thing.
"""
