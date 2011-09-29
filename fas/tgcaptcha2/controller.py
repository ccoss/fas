from turbogears import controllers, expose
import turbogears as tg
import cherrypy
from fas.tgcaptcha2 import model
import random
from cStringIO import StringIO
from Crypto.Cipher import AES
import sha
import base64
from pkg_resources import iter_entry_points
import logging
log = logging.getLogger("tgcaptcha.controller")

class CaptchaController(controllers.Controller):

    def __init__(self):
        key = tg.config.get('tgcaptcha.key', 'secret')
        if key == 'secret':
            log.warning('You need to set the "tgcaptcha.key" value in your '
                        'config file')
        key = sha.new(key).hexdigest()[:32]
        random.seed()
        self.aes = AES.new(key, AES.MODE_ECB)
        self.jpeg_generator = None
        # find the jpeg generator
        jpeg_gen = tg.config.get('tgcaptcha.jpeg_generator', 'vanasco_dowty')
        for ep in iter_entry_points('tgcaptcha2.jpeg_generators', jpeg_gen):
            self.jpeg_generator = ep.load()
        # find the text generator
        self.text_generator = None
        txt_gen = tg.config.get('tgcaptcha.text_generator', 'random_ascii')
        for ep in iter_entry_points('tgcaptcha2.text_generators', txt_gen):
            self.text_generator = ep.load()

    def image(self, value):
        "Serve a jpeg for the given payload value."
        scp = self.model_from_payload(value)
        f = StringIO()
        if scp.label is not None and scp.label != None:
            self.jpeg_generator(scp.label, f)
        else:
            self.jpeg_generator(scp.plaintext, f)
        cherrypy.response.headers['Content-Type'] = 'image/jpeg'
        f.seek(0)
        return f.read()
    image = expose()(image)

    def create_payload(self):
        "Create a payload that uniquely identifies the captcha."
        c = model.Captcha()
        c.plaintext = self.text_generator()
        if isinstance(c.plaintext, tuple):
             c.label = "%i + %i" %(c.plaintext[0], c.plaintext[1])
             c.plaintext = str(c.plaintext[0] + c.plaintext[1])
        s = c.serialize()
        # pad shortfall with multiple Xs
        if len(s) % 16:
            pad = (16 - (len(s) % 16)) * 'X'
            s = "".join((s, pad))
        enc = self.aes.encrypt(s)
        return base64.urlsafe_b64encode(enc)

    def model_from_payload(self, ascii_payload):
        "Convert a payload to a SCPayload object."
        enc = base64.urlsafe_b64decode(ascii_payload)
        s = self.aes.decrypt(enc)
        s = s.rstrip('X')
        return model.Captcha.deserialize(s)

def attach_controller():
    "Attach the controller to the root app."
    path = tg.config.get('tgcaptcha.controller', '/captcha')
    assert path[0]=='/', "tgcaptcha.controller must start with a leading /"
    nodes = path.split('/')[1:]
    if cherrypy.root:
        controller = cherrypy.root
        for c in nodes[:-1]:
            controller =  getattr(controller, c)
        setattr(controller, nodes[-1], CaptchaController())
        log.info('Attached controller "%s" to the application' % path)

tg.startup.call_on_startup.append(attach_controller)
