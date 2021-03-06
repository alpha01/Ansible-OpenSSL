import os
from subprocess import call

KEY_STENGTH = 2048
DAYS_VALID  = 3653 # ~10 years
TMPL_GEN_PK =   "openssl genrsa -out {0}.key.pem {1}"
TMPL_GEN_REQ =  "openssl req -new -key {0}.key.pem -out {0}.req.pem -outform PEM -subj {1} -nodes"
TMPL_SIGN_REQ = "openssl ca -config openssl.cnf -in {0}/{1}.req.pem -out {0}/{1}.cert.pem -notext -batch -extensions {2}"
TMPL_PKCS12 =   "openssl pkcs12 -export -out {0}.keycert.p12 -in {0}.cert.pem -inkey {0}.key.pem -passout file:{1}"
TMPL_REVOKE = "openssl ca -config openssl.cnf -revoke {0} -keyfile private/cakey.pem -cert cacert.pem"
TMPL_GEN_CRL = "openssl ca -config openssl.cnf -gencrl -keyfile private/cakey.pem -cert cacert.pem -out crl.pem"
DEV_NULL = open('/dev/null', 'w')

class Certificate:

    def __init__(self, cadir, hostname, subj, p12password, isServerCert):
        self.cadir = self.normalize_directory_path(cadir)
        self.hostname = hostname
        self.subj = subj
        self.p12password = p12password
        self.isServerCert = isServerCert

    def normalize_directory_path(self, path):
        if path.endswith(os.sep):
            return path[:-1]
        else:
            return path

    def execute_command(self, cmd):
        call(cmd, shell=True, stdout=DEV_NULL, stderr=DEV_NULL)

    def read_file(self, filename):
        with open(filename, "r") as f:
            return f.read()

    def ensure_directory_exists(self, dir):
        if not os.path.exists(dir):
            os.mkdir(dir)

    def generate_private_key(self):
        cmd = TMPL_GEN_PK.format(self.hostname, KEY_STENGTH)
        self.execute_command(cmd)

    def generate_certificate_request(self):
        cmd = TMPL_GEN_REQ.format(self.hostname, self.subj)
        self.execute_command(cmd)

    def sign_certificate_request(self, curdir):
        os.chdir("..")
        ext = "server_ca_extensions" if self.isServerCert else "client_ca_extensions"
        cmd = TMPL_SIGN_REQ.format(curdir, self.hostname, ext)
        self.execute_command(cmd)
        os.chdir(curdir)

    def create_key_cert_PEM(self):
        keyPem = self.read_file(self.hostname + ".key.pem")
        cerPem = self.read_file(self.hostname + ".cert.pem")
        with open(self.hostname + ".keycert.pem", "w") as kcFile:
            kcFile.write(keyPem)
            kcFile.write("\n")
            kcFile.write(cerPem)

    def export_key_as_PKCS12(self):
        passwordFile = self.hostname + ".password"
        with open(passwordFile, "w") as f:
            f.write(self.p12password)
        cmd = TMPL_PKCS12.format(self.hostname, passwordFile)
        self.execute_command(cmd)
        os.remove(passwordFile)

    def get_target_path(self):
        return "server" if self.isServerCert else "client"

    def validate_config(self):
        if not os.path.exists(self.cadir):
            return dict(success=False, msg="CA directory does not exist.")
        elif not os.path.exists(self.cadir + os.sep + "cacert.pem"):
            return dict(success=False, msg="CA directory does not contain a valid CA configuration.")
        elif not "CN=" in self.subj:
            return dict(success=False, msg="Common Name (CN) not found in subject string.")
        else:
            return dict(success=True)

    def validate_removal_config(self):
        if not os.path.exists(self.cadir):
            return dict(success=False, msg="CA directory does not exist.")
        else:
            return dict(success=True)


    def create_certificate(self):

        CURDIR = os.getcwd()

        changed = False
        changes = []

        os.chdir(self.cadir)

        target_path = self.get_target_path()

        self.ensure_directory_exists(target_path)

        os.chdir(target_path)

        if not os.path.exists(self.hostname + ".key.pem"):
            self.generate_private_key()
            changes.append("Created private key for {0}.".format(self.hostname))
            changed = True

        if not os.path.exists(self.hostname + ".req.pem"):
            self.generate_certificate_request()
            changes.append("Created certificate request for {0}".format(self.hostname))
            changed = True

        if not os.path.exists(self.hostname + ".cert.pem"):
            self.sign_certificate_request(target_path)
            changes.append("Signed certificate for {0}".format(self.hostname))
            changed = True

        if not os.path.exists(self.hostname + ".keycert.pem"):
            self.create_key_cert_PEM()
            changes.append("Created key-cert PEM file for {0}".format(self.hostname))

        if not os.path.exists(self.hostname + ".keycert.p12"):
            self.export_key_as_PKCS12()
            changes.append("Created PKCS12 version of the Private Key/Certificate Pair for {0}".format(self.hostname))
            changed = True

        os.chdir(CURDIR)

        return dict(success=True, changed=changed, changes=changes)

    def revoke_certificate(self):

        CURDIR = os.getcwd()

        os.chdir("..")

        cmd = TMPL_REVOKE.format(CURDIR + os.sep + self.hostname + ".cert.pem")
        self.execute_command(cmd)

        cmd2 = TMPL_GEN_CRL
        self.execute_command(cmd2)

        os.chdir(CURDIR)


    def remove_certificate(self):

        CURDIR = os.getcwd()

        changed = False
        changes = []

        target_path = self.get_target_path()

        if not os.path.exists(target_path):
            return dict(success=True, changed=changed, changes=changes, msg="{0} does not exist, therefore cert doesn't exist.".format(target_path))

        os.chdir(target_path)

        if os.path.exists(self.hostname + ".key.pem"):
            os.remove(self.hostname + ".key.pem")
            changes.append("Removed private key for {0}.".format(self.hostname))
            changed = True

        if os.path.exists(self.hostname + ".req.pem"):
            os.remove(self.hostname + ".req.pem")
            changes.append("Removed certificate request for {0}".format(self.hostname))
            changed = True

        if os.path.exists(self.hostname + ".cert.pem"):
            self.revoke_certificate()
            os.remove(self.hostname + ".cert.pem")
            changes.append("Removed certificate for {0}".format(self.hostname))
            changed = True

        if os.path.exists(self.hostname + ".keycert.pem"):
            os.remove(self.hostname + ".keycert.pem")
            changes.append("Removed key-cert PEM file for {0}".format(self.hostname))

        if os.path.exists(self.hostname + ".keycert.p12"):
            os.remove(self.hostname + ".keycert.p12")
            changes.append("Removed PKCS12 version of the Private Key/Certificate Pair for {0}".format(self.hostname))
            changed = True

        os.chdir(CURDIR)

        return dict(success=True, changed=changed, changes=changes)