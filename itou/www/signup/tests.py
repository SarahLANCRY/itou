from allauth.account.forms import default_token_generator
from allauth.account.models import EmailConfirmationHMAC
from allauth.account.utils import user_pk_to_url_str
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.html import escape
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext as _

from itou.cities.factories import create_test_cities
from itou.cities.models import City
from itou.prescribers.factories import (
    AuthorizedPrescriberOrganizationWithMembershipFactory,
    PrescriberOrganizationFactory,
    PrescriberOrganizationWithMembershipFactory,
)
from itou.siaes.factories import SiaeFactory, SiaeWithMembershipFactory
from itou.siaes.models import Siae
from itou.users.factories import DEFAULT_PASSWORD, JobSeekerFactory
from itou.utils.address.departments import department_from_postcode
from itou.www.signup.forms import SelectSiaeForm


class SignupTest(TestCase):
    def test_allauth_signup_url_override(self):
        """Ensure that the default allauth signup URL is overridden."""
        ALLAUTH_SIGNUP_URL = reverse("account_signup")
        self.assertEqual(ALLAUTH_SIGNUP_URL, "/accounts/signup/")
        response = self.client.get(ALLAUTH_SIGNUP_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "signup/signup.html")
        response = self.client.post(ALLAUTH_SIGNUP_URL, data={"foo": "bar"})
        self.assertEqual(response.status_code, 405)


class SiaeSignupTest(TestCase):
    def get_siae_magic_link_non_flaky_prefix(self, siae):
        """
        The token in the magic link can be quite flaky throughout the tests
        thus we need this helper to get the non flaky part of the url.
        """
        return f"{reverse('signup:siae')}/{urlsafe_base64_encode(force_bytes(siae.pk))}/"

    def assert_url_is_siae_magic_link(self, url, siae):
        non_flaky_url_prefix = self.get_siae_magic_link_non_flaky_prefix(siae)
        self.assertTrue(url.startswith(non_flaky_url_prefix))

    def assert_siae_magic_link_is_in_email_body(self, siae, body):
        non_flaky_url_prefix = self.get_siae_magic_link_non_flaky_prefix(siae)
        url_domain = "http://testserver"
        self.assertIn(f"{url_domain}{non_flaky_url_prefix}", body)

    def test_select_siae_form_errors(self):
        """
        Test SelectSiaeForm errors.
        """

        # Missing email and SIRET.
        post_data = {"kind": Siae.KIND_ACI}
        form = SelectSiaeForm(data=post_data)
        form.is_valid()
        expected_error = _("Merci de renseigner un e-mail ou un numéro de SIRET connu de nos services.")
        self.assertIn(expected_error, form.errors["__all__"])

        # (email, kind) or (siret, kind) does not match any siae.
        post_data = {"email": "daniela.doe@siae.com", "siret": "12345678901234", "kind": Siae.KIND_ACI}
        form = SelectSiaeForm(data=post_data)
        form.is_valid()
        expected_error = _("Votre numéro de SIRET ou votre e-mail nous sont inconnus.")
        self.assertTrue(form.errors["__all__"][0].startswith(expected_error))

        # (email, kind) matches two siaes, (siret, kind) does not match any siae.
        user_email = "emilie.doe@siae.com"
        SiaeFactory.create_batch(2, kind=Siae.KIND_ACI, auth_email=user_email)
        post_data = {"email": user_email, "siret": "12345678901234", "kind": Siae.KIND_ACI}
        form = SelectSiaeForm(data=post_data)
        form.is_valid()
        expected_error = _("Votre e-mail est partagé par plusieurs structures")
        self.assertTrue(form.errors["__all__"][0].startswith(expected_error))

    def test_legacy_route(self):
        """
        Opening the old route without any magic link credentials
        should nicely redirect the user to the correct signup url.
        """
        url = reverse("signup:siae")
        response = self.client.get(url, follow=True)
        redirect_url, status_code = response.redirect_chain[-1]
        self.assertEqual(status_code, 302)
        next_url = reverse("signup:select_siae")
        self.assertEqual(redirect_url, next_url)
        self.assertEqual(response.status_code, 200)
        expected_message = _(
            "Ce lien d'inscription est invalide ou a expiré. " "Veuillez procéder à une nouvelle inscription."
        )
        self.assertContains(response, escape(expected_message))

    def test_siae_signup_story_of_jessica(self):
        """
        Test the following SIAE signup case:
        - email does not match any siae
        - siret matches two siaes
        - (siret, kind) matches one siae
        - existing siae already has an (admin) user
        Story and expected results:
        - new user is created, active and redirected to dashboard
        - a warning fyi-only email is sent to the admin user
        """
        user_first_name = "Jessica"
        user_email = "jessica.doe@siae.com"

        siae1 = SiaeWithMembershipFactory(kind=Siae.KIND_ETTI)

        self.assertEqual(len(siae1.active_admin_members), 1)
        existing_admin_user = siae1.active_admin_members[0]

        siae2 = SiaeFactory(kind=Siae.KIND_ACI, siret=siae1.siret)

        url = reverse("signup:select_siae")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {"email": user_email, "siret": siae1.siret, "kind": siae1.kind}
        response = self.client.post(url, data=post_data, follow=True)
        redirect_url, status_code = response.redirect_chain[-1]
        self.assertEqual(status_code, 302)
        self.assert_url_is_siae_magic_link(url=redirect_url, siae=siae1)
        self.assertEqual(response.status_code, 200)

        url = reverse("signup:siae")
        post_data = {
            # hidden fields
            "encoded_siae_id": siae1.get_encoded_siae_id(),
            "token": siae1.get_token(),
            # readonly fields
            "siret": siae1.siret,
            "kind": siae1.kind,
            "siae_name": siae1.display_name,
            # regular fields
            "first_name": user_first_name,
            "last_name": "Doe",
            "email": user_email,
            "password1": "!*p4ssw0rd123-",
            "password2": "!*p4ssw0rd123-",
        }
        response = self.client.post(url, data=post_data, follow=True)
        redirect_url, status_code = response.redirect_chain[-1]
        self.assertEqual(status_code, 302)
        next_url = reverse("dashboard:index")
        self.assertEqual(redirect_url, next_url)
        self.assertEqual(response.status_code, 200)
        new_user = get_user_model().objects.get(email=user_email)

        self.assertFalse(new_user.is_job_seeker)
        self.assertFalse(new_user.is_prescriber)
        self.assertTrue(new_user.is_siae_staff)
        self.assertTrue(new_user.is_active)
        self.assertFalse(siae1.has_admin(new_user))
        self.assertEqual(2, siae1.members.count())

        self.assertEqual(new_user.first_name, user_first_name)
        self.assertEqual(new_user.last_name, "Doe")
        self.assertEqual(new_user.email, user_email)

        # siae2 is left untouched even though it has the same siret as siae1.
        siae2 = Siae.objects.get(siret=siae2.siret, kind=siae2.kind)
        self.assertEqual(0, siae2.members.count())

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("Un nouvel utilisateur vient de rejoindre votre structure", email.subject)
        self.assertIn("Si vous ne connaissez pas cette personne veuillez nous contacter", email.body)
        self.assertIn(new_user.first_name, email.body)
        self.assertIn(new_user.last_name, email.body)
        self.assertIn(new_user.email, email.body)
        self.assertIn(siae1.display_name, email.body)
        self.assertIn(siae1.siret, email.body)
        self.assertIn(siae1.kind, email.body)
        self.assertEqual(email.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(len(email.to), 1)
        self.assertEqual(email.to[0], existing_admin_user.email)

    def test_siae_signup_story_of_jacques(self):
        """
        Test the following SIAE signup case:
        - email does not match any siae
        - siret matches two siaes
        - (siret, kind) matches one siae
        - existing siae has no user yet
        - user finally signs up with a different email
        Story and expected results:
        - email with magic link is sent to siae.email
        - siae.email opens magic link a first time to continue signup
        - siae.email opens magic link a second time to continue signup (no error)
        - new user is created, active and redirected to dashboard
        - siae.email opens magic link a third time and gets 'invalid token' error
        """
        user_first_name = "Jacques"
        user_email = "jacques.doe@siae.com"
        user_secondary_email = "jacques.doe@hotmail.com"

        siae1 = SiaeFactory(kind=Siae.KIND_ETTI)

        siae2 = SiaeFactory(kind=Siae.KIND_ACI, siret=siae1.siret)

        url = reverse("signup:select_siae")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {"email": user_email, "siret": siae1.siret, "kind": siae1.kind}
        response = self.client.post(url, data=post_data, follow=True)
        redirect_url, status_code = response.redirect_chain[-1]
        self.assertEqual(status_code, 302)
        next_url = reverse("home:hp")
        self.assertEqual(redirect_url, next_url)
        self.assertEqual(response.status_code, 200)
        expected_message = _(
            f"Nous venons de vous envoyer un e-mail à l'adresse {siae1.obfuscated_auth_email} "
            f"pour continuer votre inscription. Veuillez consulter votre boite "
            f"de réception."
        )
        self.assertContains(response, escape(expected_message))

        magic_link = siae1.signup_magic_link

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("Un nouvel utilisateur souhaite rejoindre votre structure", email.subject)
        self.assertIn("veuillez ouvrir le lien suivant pour continuer votre inscription", email.body)
        self.assert_siae_magic_link_is_in_email_body(siae=siae1, body=email.body)
        self.assertIn(siae1.display_name, email.body)
        self.assertIn(siae1.siret, email.body)
        self.assertIn(siae1.kind, email.body)
        self.assertIn(siae1.auth_email, email.body)
        self.assertNotIn(siae1.email, email.body)
        self.assertEqual(email.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(len(email.to), 1)
        self.assertEqual(email.to[0], siae1.auth_email)

        response = self.client.get(magic_link)
        self.assertEqual(response.status_code, 200)

        # no error when opening magic link a second time
        response = self.client.get(magic_link)
        self.assertEqual(response.status_code, 200)

        url = reverse("signup:siae")
        post_data = {
            # hidden fields
            "encoded_siae_id": siae1.get_encoded_siae_id(),
            "token": siae1.get_token(),
            # readonly fields
            "siret": siae1.siret,
            "kind": siae1.kind,
            "siae_name": siae1.display_name,
            # regular fields
            "first_name": user_first_name,
            "last_name": "Doe",
            "email": user_secondary_email,
            "password1": "!*p4ssw0rd123-",
            "password2": "!*p4ssw0rd123-",
        }
        response = self.client.post(url, data=post_data, follow=True)
        redirect_url, status_code = response.redirect_chain[-1]
        self.assertEqual(status_code, 302)
        next_url = reverse("dashboard:index")
        self.assertEqual(redirect_url, next_url)
        self.assertEqual(response.status_code, 200)

        self.assertFalse(get_user_model().objects.filter(email=user_email).exists())
        new_user = get_user_model().objects.get(email=user_secondary_email)

        self.assertFalse(new_user.is_job_seeker)
        self.assertFalse(new_user.is_prescriber)
        self.assertTrue(new_user.is_siae_staff)
        self.assertTrue(new_user.is_active)
        self.assertTrue(siae1.has_admin(new_user))
        self.assertEqual(1, siae1.members.count())
        self.assertEqual(new_user.first_name, user_first_name)
        self.assertEqual(new_user.last_name, "Doe")

        self.assertNotEqual(new_user.email, user_email)
        self.assertEqual(new_user.email, user_secondary_email)

        # siae2 is left untouched even though it has the same siret as siae1.
        siae2 = Siae.objects.get(siret=siae2.siret, kind=siae2.kind)
        self.assertEqual(0, siae2.members.count())

        self.client.logout()

        # magic link is no longer valid because siae.members.count() has changed
        response = self.client.get(magic_link, follow=True)
        redirect_url, status_code = response.redirect_chain[-1]
        self.assertEqual(status_code, 302)
        next_url = reverse("signup:select_siae")
        self.assertEqual(redirect_url, next_url)
        self.assertEqual(response.status_code, 200)
        expected_message = _(
            "Ce lien d'inscription est invalide ou a expiré. " "Veuillez procéder à une nouvelle inscription."
        )
        self.assertContains(response, escape(expected_message))

    def test_siae_signup_story_of_david(self):
        """
        Test the following SIAE signup case:
        - (email, kind) matches two siaes
        - (siret, kind) matches one siae, different from the two above
        - existing siae already has a user
        Story and expected results:
        - priority is given to siret match over email match
        - new user is created, active and redirected to dashboard
        - user is associated to siae matching siret
        """
        user_first_name = "David"
        user_email = "david.doe@siae.com"

        shared_siae_kind = Siae.KIND_ACI

        siae1 = SiaeFactory(kind=shared_siae_kind, auth_email=user_email)  # noqa F841

        siae2 = SiaeFactory(kind=shared_siae_kind, auth_email=user_email)  # noqa F841

        siae3 = SiaeWithMembershipFactory(kind=shared_siae_kind, siret="12345678901234")

        url = reverse("signup:select_siae")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {"email": user_email, "siret": siae3.siret, "kind": shared_siae_kind}
        response = self.client.post(url, data=post_data, follow=True)
        redirect_url, status_code = response.redirect_chain[-1]
        self.assertEqual(status_code, 302)
        self.assert_url_is_siae_magic_link(url=redirect_url, siae=siae3)
        self.assertEqual(response.status_code, 200)

        url = reverse("signup:siae")
        post_data = {
            # hidden fields
            "encoded_siae_id": siae3.get_encoded_siae_id(),
            "token": siae3.get_token(),
            # readonly fields
            "siret": siae3.siret,
            "kind": shared_siae_kind,
            "siae_name": siae3.display_name,
            # regular fields
            "first_name": user_first_name,
            "last_name": "Doe",
            "email": user_email,
            "password1": "!*p4ssw0rd123-",
            "password2": "!*p4ssw0rd123-",
        }
        response = self.client.post(url, data=post_data, follow=True)
        redirect_url, status_code = response.redirect_chain[-1]
        self.assertEqual(status_code, 302)
        next_url = reverse("dashboard:index")
        self.assertEqual(redirect_url, next_url)
        self.assertEqual(response.status_code, 200)
        new_user = get_user_model().objects.get(email=user_email)

        self.assertFalse(new_user.is_job_seeker)
        self.assertFalse(new_user.is_prescriber)
        self.assertTrue(new_user.is_siae_staff)
        self.assertTrue(new_user.is_active)
        self.assertFalse(siae3.has_admin(new_user))
        self.assertEqual(2, siae3.members.count())

        self.assertEqual(new_user.first_name, user_first_name)
        self.assertEqual(new_user.last_name, "Doe")
        self.assertEqual(new_user.email, user_email)

    def test_siae_signup_story_of_bernadette(self):
        """
        Test the following SIAE signup case:
        - (email, kind) matches one siae
        - (siret, kind) does not match any siae
        - existing siae already has a user
        Story and expected results:
        - new user is created, active and redirected to dashboard
        - user is associated to siae matching email
        """
        user_first_name = "Bernadette"
        user_email = "bernadette.doe@siae.com"

        siae = SiaeWithMembershipFactory(auth_email=user_email)

        unknown_siret = "12345678901234"

        url = reverse("signup:select_siae")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {"email": user_email, "siret": unknown_siret, "kind": siae.kind}
        response = self.client.post(url, data=post_data, follow=True)
        redirect_url, status_code = response.redirect_chain[-1]
        self.assertEqual(status_code, 302)
        self.assert_url_is_siae_magic_link(url=redirect_url, siae=siae)
        self.assertEqual(response.status_code, 200)

        url = reverse("signup:siae")
        post_data = {
            # hidden fields
            "encoded_siae_id": siae.get_encoded_siae_id(),
            "token": siae.get_token(),
            # readonly fields
            "siret": siae.siret,
            "kind": siae.kind,
            "siae_name": siae.display_name,
            # regular fields
            "first_name": user_first_name,
            "last_name": "Doe",
            "email": user_email,
            "password1": "!*p4ssw0rd123-",
            "password2": "!*p4ssw0rd123-",
        }
        response = self.client.post(url, data=post_data, follow=True)
        redirect_url, status_code = response.redirect_chain[-1]
        self.assertEqual(status_code, 302)
        next_url = reverse("dashboard:index")
        self.assertEqual(redirect_url, next_url)
        self.assertEqual(response.status_code, 200)
        new_user = get_user_model().objects.get(email=user_email)

        self.assertFalse(new_user.is_job_seeker)
        self.assertFalse(new_user.is_prescriber)
        self.assertTrue(new_user.is_siae_staff)
        self.assertTrue(new_user.is_active)
        self.assertFalse(siae.has_admin(new_user))
        self.assertEqual(2, siae.members.count())

        self.assertEqual(new_user.first_name, user_first_name)
        self.assertEqual(new_user.last_name, "Doe")
        self.assertEqual(new_user.email, user_email)

    def test_siae_signup_story_of_leonard(self):
        """
        Test the following SIAE signup case:
        - (email, kind) matches one siae
        - (siret, kind) matches one siae (a different one)
        - existing siae already has a user
        Story and expected results:
        - priority is given to siret match over email match
        - new user is created, active and redirected to dashboard
        - user is associated to siae matching siret
        """
        user_first_name = "Leonard"
        user_email = "leonard.doe@siae.com"

        shared_siae_kind = Siae.KIND_GEIQ

        siae1 = SiaeFactory(kind=shared_siae_kind, auth_email=user_email)  # noqa F841

        siae2 = SiaeWithMembershipFactory(kind=shared_siae_kind)

        url = reverse("signup:select_siae")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {"email": user_email, "siret": siae2.siret, "kind": shared_siae_kind}
        response = self.client.post(url, data=post_data, follow=True)
        redirect_url, status_code = response.redirect_chain[-1]
        self.assertEqual(status_code, 302)
        self.assert_url_is_siae_magic_link(url=redirect_url, siae=siae2)
        self.assertEqual(response.status_code, 200)

        url = reverse("signup:siae")
        post_data = {
            # hidden fields
            "encoded_siae_id": siae2.get_encoded_siae_id(),
            "token": siae2.get_token(),
            # readonly fields
            "siret": siae2.siret,
            "kind": shared_siae_kind,
            "siae_name": siae2.display_name,
            # regular fields
            "first_name": user_first_name,
            "last_name": "Doe",
            "email": user_email,
            "password1": "!*p4ssw0rd123-",
            "password2": "!*p4ssw0rd123-",
        }
        response = self.client.post(url, data=post_data, follow=True)
        redirect_url, status_code = response.redirect_chain[-1]
        self.assertEqual(status_code, 302)
        next_url = reverse("dashboard:index")
        self.assertEqual(redirect_url, next_url)
        self.assertEqual(response.status_code, 200)
        new_user = get_user_model().objects.get(email=user_email)

        self.assertFalse(new_user.is_job_seeker)
        self.assertFalse(new_user.is_prescriber)
        self.assertTrue(new_user.is_siae_staff)
        self.assertTrue(new_user.is_active)
        self.assertFalse(siae2.has_admin(new_user))
        self.assertEqual(2, siae2.members.count())

        self.assertEqual(new_user.first_name, user_first_name)
        self.assertEqual(new_user.last_name, "Doe")
        self.assertEqual(new_user.email, user_email)


class JobSeekerSignupTest(TestCase):
    def setUp(self):
        create_test_cities(["67"], num_per_department=1)

    def test_job_seeker_signup(self):
        """Job-seeker signup."""

        url = reverse("signup:job_seeker")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        password = "!*p4ssw0rd123-"
        address_line_1 = "Test adresse"
        address_line_2 = "Test adresse complémentaire"
        city = City.objects.first()
        post_code = city.post_codes[0]

        post_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@siae.com",
            "password1": password,
            "password2": password,
            "address_line_1": address_line_1,
            "address_line_2": address_line_2,
            "post_code": post_code,
            "city_name": city.name,
            "city": city.slug,
        }

        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("account_email_verification_sent"))

        # Check `User` state.
        user = get_user_model().objects.get(email=post_data["email"])
        self.assertTrue(user.is_job_seeker)
        self.assertFalse(user.is_prescriber)
        self.assertFalse(user.is_siae_staff)
        self.assertEquals(user.address_line_1, address_line_1)
        self.assertEquals(user.address_line_2, address_line_2)
        self.assertEquals(user.post_code, post_code)
        self.assertEquals(user.city, city.name)
        self.assertEquals(user.department, department_from_postcode(post_code))
        # Check `EmailAddress` state.
        self.assertEqual(user.emailaddress_set.count(), 1)
        user_email = user.emailaddress_set.first()
        self.assertFalse(user_email.verified)

        # Check sent email.
        confirm_email_url = reverse("account_confirm_email", kwargs={"key": EmailConfirmationHMAC(user_email).key})
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("Confirmer l'adresse email pour la Plateforme de l'inclusion", email.subject)
        self.assertIn("Pour confirmer que vous en êtes bien le propriétaire", email.body)
        self.assertEqual(email.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(len(email.to), 1)
        self.assertEqual(email.to[0], user.email)
        self.assertIn(confirm_email_url, email.body)

        # User cannot log in until confirmation.
        post_data = {"login": user.email, "password": password}
        url = reverse("account_login")
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("account_email_verification_sent"))

        # Confirm email.
        confirm_email_url = reverse("account_confirm_email", kwargs={"key": EmailConfirmationHMAC(user_email).key})
        response = self.client.post(confirm_email_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("account_login"))
        user_email = user.emailaddress_set.first()
        self.assertTrue(user_email.verified)

        # User can log in after confirmation.
        post_data = {"login": user.email, "password": password}
        response = self.client.post(reverse("account_login"), data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:index"))


class PrescriberSignupTest(TestCase):
    def test_prescriber_signup_without_code_nor_organization(self):
        """Prescriber signup without code nor organization."""

        url = reverse("signup:prescriber")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        password = "!*p4ssw0rd123-"

        post_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@prescriber.com",
            "password1": password,
            "password2": password,
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("account_email_verification_sent"))

        # Check `User` state.
        user = get_user_model().objects.get(email=post_data["email"])
        self.assertFalse(user.is_job_seeker)
        self.assertTrue(user.is_prescriber)
        self.assertFalse(user.is_siae_staff)
        # Check `EmailAddress` state.
        self.assertEqual(user.emailaddress_set.count(), 1)
        user_email = user.emailaddress_set.first()
        self.assertFalse(user_email.verified)

        # Check sent email.
        confirm_email_url = reverse("account_confirm_email", kwargs={"key": EmailConfirmationHMAC(user_email).key})
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("Confirmer l'adresse email pour la Plateforme de l'inclusion", email.subject)
        self.assertIn("Pour confirmer que vous en êtes bien le propriétaire", email.body)
        self.assertEqual(email.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(len(email.to), 1)
        self.assertEqual(email.to[0], user.email)
        self.assertIn(confirm_email_url, email.body)

        # User cannot log in until confirmation.
        post_data = {"login": user.email, "password": password}
        url = reverse("account_login")
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("account_email_verification_sent"))

        # Confirm email.
        confirm_email_url = reverse("account_confirm_email", kwargs={"key": EmailConfirmationHMAC(user_email).key})
        response = self.client.post(confirm_email_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("account_login"))
        user_email = user.emailaddress_set.first()
        self.assertTrue(user_email.verified)

        # User can log in after confirmation.
        post_data = {"login": user.email, "password": password}
        response = self.client.post(reverse("account_login"), data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:index"))

    def test_prescriber_signup_with_code_to_unauthorized_organization(self):
        """
        Prescriber signup with a code to join an unauthorized organization.
        Organization has a pre-existing admin user who is notified of the signup.
        """

        organization = PrescriberOrganizationWithMembershipFactory()
        existing_user = organization.members.get()

        url = reverse("signup:prescriber")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        password = "!*p4ssw0rd123-"

        post_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@prescriber.com",
            "password1": password,
            "password2": password,
            "secret_code": organization.secret_code,
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("account_email_verification_sent"))

        # Check `User` state.
        user = get_user_model().objects.get(email=post_data["email"])
        self.assertFalse(user.is_job_seeker)
        self.assertTrue(user.is_prescriber)
        self.assertFalse(user.is_siae_staff)
        self.assertIn(user, organization.members.all())
        self.assertEqual(2, organization.members.count())
        membership = user.prescribermembership_set.get(organization=organization)
        self.assertFalse(membership.is_admin)
        # Check `EmailAddress` state.
        self.assertEqual(user.emailaddress_set.count(), 1)
        user_email = user.emailaddress_set.first()
        self.assertFalse(user_email.verified)

        # Check sent emails.
        self.assertEqual(len(mail.outbox), 2)
        subjects = [email.subject for email in mail.outbox]
        self.assertIn("Un nouvel utilisateur vient de rejoindre votre organisation", subjects)
        self.assertIn("Confirmer l'adresse email pour la Plateforme de l'inclusion", subjects)

        # Confirm email.
        confirm_email_url = reverse("account_confirm_email", kwargs={"key": EmailConfirmationHMAC(user_email).key})
        response = self.client.post(confirm_email_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("account_login"))
        user_email = user.emailaddress_set.first()
        self.assertTrue(user_email.verified)

        # User can log in after confirmation.
        post_data = {"login": user.email, "password": password}
        response = self.client.post(reverse("account_login"), data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:index"))

    def test_second_member_signup_without_code_to_authorized_organization(self):
        """
        A second user signup to join an authorized organization.
        First one is notified when second one signs up.
        """

        # Create an authorized organization with one admin.
        authorized_organization = AuthorizedPrescriberOrganizationWithMembershipFactory()
        self.assertEqual(1, authorized_organization.members.count())
        first_user = authorized_organization.members.first()
        membership = first_user.prescribermembership_set.get(organization=authorized_organization)
        self.assertTrue(membership.is_admin)

        # A second user wants to join the authorized organization.
        url = reverse("signup:prescriber")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        password = "!*p4ssw0rd123-"

        post_data = {
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane.doe@prescriber.com",
            "password1": password,
            "password2": password,
            "authorized_organization": authorized_organization.pk,
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("account_email_verification_sent"))

        # Check `User` state.
        second_user = get_user_model().objects.get(email=post_data["email"])
        self.assertFalse(second_user.is_job_seeker)
        self.assertFalse(second_user.is_siae_staff)
        self.assertTrue(second_user.is_prescriber)
        # Check `Membership` state.
        self.assertIn(second_user, authorized_organization.members.all())
        self.assertEqual(2, authorized_organization.members.count())
        self.assertEqual(1, second_user.prescriberorganization_set.count())
        membership = second_user.prescribermembership_set.get(organization=authorized_organization)
        self.assertFalse(membership.is_admin)

        # Check sent emails.
        self.assertEqual(len(mail.outbox), 2)
        subjects = [email.subject for email in mail.outbox]
        self.assertIn("Un nouvel utilisateur vient de rejoindre votre organisation", subjects)
        self.assertIn("Confirmer l'adresse email pour la Plateforme de l'inclusion", subjects)


class PasswordResetTest(TestCase):
    def test_password_reset_flow(self):

        user = JobSeekerFactory()

        # Ask for password reset.
        url = reverse("account_reset_password")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        post_data = {"email": user.email}
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("account_reset_password_done"))

        # Check sent email.
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("Réinitialisation de votre mot de passe", email.subject)
        self.assertIn("Vous pouvez ignorer ce message en toute sécurité", email.body)
        self.assertEqual(email.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(len(email.to), 1)
        self.assertEqual(email.to[0], user.email)

        # Change forgotten password.
        uidb36 = user_pk_to_url_str(user)
        key = default_token_generator.make_token(user)
        password_change_url = reverse("account_reset_password_from_key", kwargs={"uidb36": uidb36, "key": key})
        response = self.client.get(password_change_url)
        password_change_url_with_hidden_key = response.url
        post_data = {"password1": "mlkjhgfdsq2", "password2": "mlkjhgfdsq2"}
        response = self.client.post(password_change_url_with_hidden_key, data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("account_reset_password_from_key_done"))

        # User can log in with his new password.
        self.assertTrue(self.client.login(username=user.email, password="mlkjhgfdsq2"))
        self.client.logout()


class PasswordChangeTest(TestCase):
    def test_password_change_flow(self):
        """
        Ensure that the default allauth account_change_password URL is overridden
        and redirects to the right place.
        """

        user = JobSeekerFactory()
        self.assertTrue(self.client.login(username=user.email, password=DEFAULT_PASSWORD))

        # Change password.
        url = reverse("account_change_password")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        post_data = {"oldpassword": DEFAULT_PASSWORD, "password1": "mlkjhgfdsq2", "password2": "mlkjhgfdsq2"}
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("dashboard:index"))

        # User can log in with his new password.
        self.client.logout()
        self.assertTrue(self.client.login(username=user.email, password="mlkjhgfdsq2"))
        self.client.logout()


class UserEmailUniquenessTest(TestCase):
    def test_user_email_uniqueness(self):
        """Test case insensitive uniqueness of user email"""
        email_lowercase = "john.doe@siae.com"
        email_mixedcase = "JoHn.DoE@SiAe.cOm"
        email_uppercase = "JOHN.DOE@SIAE.com"
        email_different = "XoHn.DoE@SiAe.cOm"

        url = reverse("signup:job_seeker")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": email_lowercase,
            "password1": "!*p4ssw0rd123-",
            "password2": "!*p4ssw0rd123-",
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:index"))

        user = get_user_model().objects.get(email=post_data["email"])
        self.assertTrue(user.is_job_seeker)
        self.assertFalse(user.is_prescriber)
        self.assertFalse(user.is_siae_staff)

        self.client.logout()

        post_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": email_lowercase,
            "password1": "!*p4ssw0rd123-",
            "password2": "!*p4ssw0rd123-",
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "Un autre utilisateur utilise déjà cette adresse e-mail.")

        post_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": email_mixedcase,
            "password1": "!*p4ssw0rd123-",
            "password2": "!*p4ssw0rd123-",
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "Un autre utilisateur utilise déjà cette adresse e-mail.")

        post_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": email_uppercase,
            "password1": "!*p4ssw0rd123-",
            "password2": "!*p4ssw0rd123-",
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "Un autre utilisateur utilise déjà cette adresse e-mail.")

        post_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": email_different,
            "password1": "!*p4ssw0rd123-",
            "password2": "!*p4ssw0rd123-",
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:index"))
