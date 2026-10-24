"""Change the default GNOME keyring password without exporting its secrets."""
import json
import sys

import dbus


bus = dbus.SessionBus()
service_object = bus.get_object('org.freedesktop.secrets', '/org/freedesktop/secrets')
service = dbus.Interface(service_object, 'org.freedesktop.Secret.Service')
collection = service.ReadAlias('default')
if collection == '/':
    raise RuntimeError('No default keyring exists')

_, session = service.OpenSession('plain', dbus.String('', variant_level=1))
internal = dbus.Interface(service_object, 'org.gnome.keyring.InternalUnsupportedGuiltRiddenInterface')


def secret(password):
    return dbus.Struct((session, dbus.ByteArray(b''), dbus.ByteArray(password), 'text/plain'), signature='oayays')


try:
    password = b'' if sys.argv[1] == 'probe' else sys.stdin.buffer.read()
    try:
        internal.ChangeWithMasterPassword(collection, secret(password), secret(b''))
    except dbus.DBusException as error:
        if sys.argv[1] == 'probe' and error.get_dbus_name() == 'org.gnome.keyring.Error.Denied':
            print(json.dumps({'needs_password': True}))
        else:
            raise
    else:
        print(json.dumps({'needs_password': False}))
finally:
    dbus.Interface(bus.get_object('org.freedesktop.secrets', session), 'org.freedesktop.Secret.Session').Close()
