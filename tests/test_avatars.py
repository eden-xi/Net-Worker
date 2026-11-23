from io import BytesIO

from PIL import Image

ALEX = "alex@example.com"
PRIYA = "priya.pm@example.com"


def image_bytes(fmt="PNG", size=(640, 480), exif=None):
    buffer = BytesIO()
    image = Image.new("RGB", size, (161, 0, 255))
    kwargs = {"exif": exif} if exif else {}
    image.save(buffer, fmt, **kwargs)
    return buffer.getvalue()


def upload(client, headers, data, name="me.png"):
    return client.put("/me/avatar", files={"file": (name, data, "image/png")}, headers=headers)


def test_upload_crops_to_square_webp_and_serves_it(client, as_user):
    alex = as_user(ALEX)
    response = upload(client, alex, image_bytes())

    assert response.status_code == 200, response.text
    me = response.json()
    assert me["avatar"]

    picture = client.get(f"/users/{me['id']}/avatar", headers=as_user(PRIYA))
    assert picture.status_code == 200
    assert picture.headers["content-type"] == "image/webp"
    assert "private" in picture.headers["cache-control"]

    with Image.open(BytesIO(picture.content)) as image:
        assert image.size == (256, 256)


def test_metadata_is_stripped(client, as_user):
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"
    alex = as_user(ALEX)
    me = upload(client, alex, image_bytes("JPEG", exif=exif.tobytes()), "me.jpg").json()

    picture = client.get(f"/users/{me['id']}/avatar", headers=alex).content
    assert b"SecretCameraMaker" not in picture


def test_replacing_and_removing(client, as_user):
    alex = as_user(ALEX)
    first = upload(client, alex, image_bytes()).json()["avatar"]
    second = upload(client, alex, image_bytes(size=(300, 300))).json()["avatar"]
    assert first != second

    removed = client.delete("/me/avatar", headers=alex).json()
    assert removed["avatar"] is None
    assert client.get(f"/users/{removed['id']}/avatar", headers=alex).status_code == 404


def test_non_images_rejected(client, as_user):
    alex = as_user(ALEX)
    assert upload(client, alex, b"<svg onload=alert(1)>", "x.svg").status_code == 400
    assert upload(client, alex, b"%PDF-1.4 not an image", "x.png").status_code == 400
    assert upload(client, alex, b"").status_code == 400


def test_avatar_requires_sign_in(client, as_user):
    me = upload(client, as_user(ALEX), image_bytes()).json()
    assert client.get(f"/users/{me['id']}/avatar").status_code == 401


def test_avatars_listed_for_applicants(client, as_user):
    alex, priya = as_user(ALEX), as_user(PRIYA)
    upload(client, alex, image_bytes())

    project = client.get("/pm/projects", headers=priya).json()[0]
    client.post("/applications", data={"project_id": project["id"]}, headers=alex)

    applicant = client.get(f"/pm/projects/{project['id']}/applications", headers=priya).json()[0]
    assert applicant["avatar"] and applicant["user_id"]
