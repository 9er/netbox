from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError

from extras.registry import registry
from netbox.search.backends import search_backend


class Command(BaseCommand):
    help = 'Reindex objects for search'

    def add_arguments(self, parser):
        parser.add_argument(
            'args',
            metavar='app_label[.ModelName]',
            nargs='*',
            help='One or more apps or models to reindex',
        )

    def _get_indexers(self, *model_names):
        indexers = {}

        # No models specified; pull in all registered indexers
        if not model_names:
            for idx in registry['search'].values():
                indexers[idx.model] = idx

        # Return only indexers for the specified models
        else:
            for label in model_names:
                try:
                    app_label, model_name = label.lower().split('.')
                except ValueError:
                    raise CommandError(
                        f"Invalid model: {label}. Model names must be in the format <app_label>.<model_name>."
                    )
                try:
                    idx = registry['search'][f'{app_label}.{model_name}']
                    indexers[idx.model] = idx
                except KeyError:
                    raise CommandError(f"No indexer registered for {label}")

        return indexers

    def handle(self, *model_labels, **kwargs):

        # Determine which models to reindex
        indexers = self._get_indexers(*model_labels)
        if not indexers:
            raise CommandError("No indexers found!")
        self.stdout.write(f'Reindexing {len(indexers)} models.')

        # Clear all cached values for the specified models
        self.stdout.write('Clearing cached values... ', ending='')
        self.stdout.flush()
        content_types = [
            ContentType.objects.get_for_model(model) for model in indexers.keys()
        ]
        deleted_count = search_backend.clear(content_types)
        self.stdout.write(f'{deleted_count} entries deleted.')

        # Index models
        self.stdout.write('Indexing models')
        for model, idx in indexers.items():
            app_label = model._meta.app_label
            model_name = model._meta.model_name
            self.stdout.write(f'  {app_label}.{model_name}... ', ending='')
            self.stdout.flush()
            i = search_backend.cache(model.objects.iterator(), remove_existing=False)
            if i:
                self.stdout.write(f'{i} entries cached.')
            else:
                self.stdout.write(f'None found.')

        msg = f'Completed.'
        if total_count := search_backend.size:
            msg += f' Total entries: {total_count}'
        self.stdout.write(msg, self.style.SUCCESS)
