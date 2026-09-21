"""Process the approved WhatsApp queue once. Suitable for a cPanel scheduled command.
Disabled unless WHATSAPP_AUTO_SEND=true. Requires a homologated provider adapter.
"""
import os
from app.core.database import SessionLocal
from app.models.workflow import Outbox
from app.api.workflow import dispatch
from app.services.whatsapp_service import whatsapp_service

def run_once():
    if os.getenv('WHATSAPP_AUTO_SEND','false').lower()!='true' or not whatsapp_service.configured():
        return {'processed':0,'status':'disabled'}
    processed=0
    with SessionLocal() as db:
        # Atomic pending -> sending transition inside dispatch prevents duplicate claims.
        ids=[row.id for row in db.query(Outbox).filter_by(status='pending').order_by(Outbox.id).limit(50).all()]
        for message_id in ids:
            try:
                dispatch(message_id,db)
                processed+=1
            except Exception:
                db.rollback()
    return {'processed':processed,'status':'completed'}

if __name__=='__main__':
    print(run_once())
