from collections import OrderedDict
from django.conf import settings
from otree.models import Session
from otree.models_concrete import RoomSession
from django.core.urlresolvers import reverse

class Room(object):

    def __init__(self, name, display_name, participant_label_file=None):
        self.participant_label_file = participant_label_file
        self.name = name
        self.display_name = display_name

    def has_session(self):
        return self.session is not None

    @property
    def session(self):
        try:
            session_pk = RoomSession.objects.get(room_name=self.name).session_pk
            return Session.objects.get(pk=session_pk)
        except (RoomSession.DoesNotExist, Session.DoesNotExist):
            return None

    @session.setter
    def session(self, session):
        if session is None:
            RoomSession.objects.filter(room_name=self.name).delete()
        else:
            room_session, created = RoomSession.objects.get_or_create(room_name=self.name)
            room_session.session_pk = session.pk
            room_session.save()

    def has_participant_labels(self):
        return bool(self.participant_label_file)

    def get_participant_labels(self):
        if self.has_participant_labels():
            with open(self.participant_label_file) as f:
                labels = [line.strip() for line in f if line.strip()]
                return labels
        raise Exception('no guestlist')

    def url(self):
        return reverse('room', args=(self.name,))

    def url_close(self):
        return reverse('close_room', args=(self.name,))

ROOM_DICT = OrderedDict()
for room in settings.ROOMS:
    ROOM_DICT[room['name']] = Room(room['name'], room['display_name'], room.get('participant_label_file'))