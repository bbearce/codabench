import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.timezone import now

from utils.data import PathWrapper
from utils.storage import BundleStorage


class Data(models.Model):
    """Data models are unqiue based on name + created_by. If no name is given, then there is no uniqueness to enforce"""

    # It's useful to have these defaults map to the YAML names for these, like `scoring_program`
    INGESTION_PROGRAM = 'ingestion_program'
    INPUT_DATA = 'input_data'
    PUBLIC_DATA = 'public_data'
    REFERENCE_DATA = 'reference_data'
    SCORING_PROGRAM = 'scoring_program'
    STARTING_KIT = 'starting_kit'
    COMPETITION_BUNDLE = 'competition_bundle'
    SUBMISSION = 'submission'
    SOLUTION = 'solution'

    TYPES = (
        (INGESTION_PROGRAM, 'Ingestion Program',),
        (INPUT_DATA, 'Input Data',),
        (PUBLIC_DATA, 'Public Data',),
        (REFERENCE_DATA, 'Reference Data',),
        (SCORING_PROGRAM, 'Scoring Program',),
        (STARTING_KIT, 'Starting Kit',),
        (COMPETITION_BUNDLE, 'Competition Bundle',),
        (SUBMISSION, 'Submission',),
        (SOLUTION, 'Solution',),
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING)
    created_when = models.DateTimeField(default=now)
    name = models.CharField(max_length=255, null=True, blank=True)
    type = models.CharField(max_length=64, choices=TYPES)
    description = models.TextField(null=True, blank=True)
    data_file = models.FileField(
        upload_to=PathWrapper('dataset'),
        storage=BundleStorage,
        null=True,
        blank=True
    )
    key = models.UUIDField(default=uuid.uuid4, blank=True, unique=True)
    is_public = models.BooleanField(default=False)
    upload_completed_successfully = models.BooleanField(default=False)

    # This is true if the Data model was created as part of unpacking a competition. Competition bundles themselves
    # are NOT marked True, since they are not created by unpacking!
    was_created_by_competition = models.BooleanField(default=False)

    # TODO: add Model manager that automatically filters out upload_completed_successfully=False from queries
    # TODO: remove upload_completed_successfully=False after 3 days ???

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = f"{self.created_by.username} - {self.type}"
        return super().save(*args, **kwargs)

    @property
    def in_use(self):
        from tasks.models import Task
        tasks = Task.objects.filter(Q(ingestion_program=self) | Q(input_data=self) | Q(reference_data=self) | Q(scoring_program=self)).prefetch_related('phases')
        phases_from_tasks = [phase for task in tasks for phase in task.phases.all()]
        from competitions.models import Phase
        phases = Phase.objects.filter(Q(ingestion_program=self) | Q(input_data=self) | Q(reference_data=self) | Q(scoring_program=self)).prefetch_related('competition')
        print(tasks)
        print(phases_from_tasks)
        print(phases)
        task_competitions = [phase.competition.pk for phase in phases_from_tasks if phase.competition]
        phase_competitions = [phase.competition.pk for phase in phases if phase.competition]
        competition_set = list(set(task_competitions + phase_competitions))
        is_used = bool(competition_set)
        return {'value': is_used,
                'competitions': competition_set}


    def __str__(self):
        return self.name or ''


class DataGroup(models.Model):
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING)
    created_when = models.DateTimeField(default=now)
    name = models.CharField(max_length=255)
    datas = models.ManyToManyField(Data, related_name="groups")
