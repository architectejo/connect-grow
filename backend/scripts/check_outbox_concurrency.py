"""Vérification MANUELLE de la concurrence de l'outbox (ADR 0003) : plusieurs `dispatch_outbox`
simultanés sur un vrai fichier SQLite, sans doublon ni « database is locked ».

À refaire avant le passage à MySQL (le verrouillage y est différent) et après toute modification de
`platform_core/services.py`. Non lancé par `manage.py test` (la base de test en mémoire ne supporte pas
les accès parallèles).

    cd backend
    SECRET_KEY=une-valeur NUM_PROXIES=1 python scripts/check_outbox_concurrency.py [--events 60] [--workers 3]

Le script crée une base temporaire (jamais la base de développement), y sème N contacts, lance les
workers en parallèle puis vérifie : N messages, N notifications, toutes les livraisons traitées, aucun
échec. Code de sortie 0 si tout est exact, 1 sinon.
"""
import argparse
import os
import subprocess
import sys
import tempfile

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARK = 'CHECK_OUTBOX_TEMP_DB'


def seed(count):
    from apps.catalog.models import Category, City, Commune
    from apps.common.factories import make_test_image, owner_kwargs
    from apps.identity.models import User
    from apps.marketplace import services
    from apps.marketplace.models import Offer

    city = City.objects.create(name='Kinshasa')
    commune = Commune.objects.create(city=city, name='Gombe')
    category = Category.objects.create(name='Catégorie', slug='categorie')
    seller = User.objects.create_user(email='vendeur@example.com', password='x', full_name='Vendeur')
    offer = Offer.objects.create(
        **owner_kwargs(seller), category_id=category.id, commune_id=commune.id, title='Annonce',
        description='Description suffisamment longue pour le test.', price=1, main_image=make_test_image(),
    )
    for n in range(count):
        buyer = User.objects.create_user(email=f'acheteur{n}@example.com', password='x', full_name=f'Acheteur {n}')
        services.create_contact_event(offer=offer, sender=buyer, message=f'Message {n}')
    print(f'{count} contacts semés.')


def verify(count):
    from apps.messaging.models import Message
    from apps.notifications.models import Notification
    from apps.platform_core.models import OutboxDelivery

    statuses = {}
    for status in OutboxDelivery.objects.values_list('status', flat=True):
        statuses[status] = statuses.get(status, 0) + 1
    messages, notifications = Message.objects.count(), Notification.objects.count()
    print(f'messages={messages} notifications={notifications} livraisons={statuses}')
    ok = messages == count and notifications == count and statuses == {'done': 2 * count}
    print('OK : aucun doublon, aucune perte.' if ok else 'ÉCHEC : compteurs inattendus.')
    return 0 if ok else 1


def child_main(action, count):
    if not os.environ.get(MARK):
        sys.exit('Refus : ce mode ne s\'exécute que sur la base temporaire créée par le script.')
    sys.path.insert(0, BACKEND)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
    import django

    django.setup()
    if action == 'seed':
        seed(count)
        return 0
    return verify(count)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--events', type=int, default=60)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--child', choices=['seed', 'verify'], help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        sys.exit(child_main(args.child, args.events))

    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, DB_ENGINE='sqlite', DB_NAME=os.path.join(tmp, 'concurrency.sqlite3'),
                   OUTBOX_INLINE_DISPATCH='False', **{MARK: '1'})
        manage = [sys.executable, os.path.join(BACKEND, 'manage.py')]
        me = [sys.executable, os.path.abspath(__file__), '--events', str(args.events)]
        subprocess.run(manage + ['migrate', '-v0'], cwd=BACKEND, env=env, check=True)
        subprocess.run(me + ['--child', 'seed'], cwd=BACKEND, env=env, check=True)
        workers = [subprocess.Popen(manage + ['dispatch_outbox', '--max-seconds', '120'], cwd=BACKEND, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                   for _ in range(args.workers)]
        failed = False
        for worker in workers:
            out, err = worker.communicate()
            print(out.strip())
            if worker.returncode != 0 or 'locked' in err.lower() or 'Traceback' in err:
                failed = True
                print(err)
        result = subprocess.run(me + ['--child', 'verify'], cwd=BACKEND, env=env)
        sys.exit(1 if failed else result.returncode)


if __name__ == '__main__':
    main()
