"""Deliberately disabled ElmTree writer.

Until ElmTree publishes/authorizes integration documentation and company grants
pilot permission, no route may push data into ElmTree. 'CSV-ready' is NOT API support.
"""
class IntegrationNotAuthorized(PermissionError):pass


def send_to_elmtree(*args,**kwargs):
    raise IntegrationNotAuthorized('ElmTree write integration unavailable: vendor interface and company approval required')


def export_review_packet(records):
    if not isinstance(records,list) or len(records)>1000:raise ValueError('Invalid review packet')
    return {'schema':'cmt-neutral-handoff-v2.0','mode':'REVIEW_ONLY',
            'destination':'NO_CONNECTED_DESTINATION', 'records':records,
            'warning':'This format is not verified or approved by ElmTree. No automatic import or material acceptance.'}
