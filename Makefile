
release:
	find . -name __pycache__ -type d -exec rm -rf "{}" \;
	zip -r payment_twikey-16.0.2.0.0-SNAPSHOT.zip payment_twikey README.md
