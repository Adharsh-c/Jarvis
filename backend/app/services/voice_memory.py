"""Small helper for the V6 voice bridge's shared memory profile."""
from sqlalchemy.orm import Session
from ..models import Memory

def add_voice_memory(db: Session, content: str, kind: str = "note"):
    item = Memory(profile="voice", kind=kind[:40], content=content.strip(), enabled=True)
    db.add(item); db.commit(); db.refresh(item)
    return item
