from app.services.service_validator_person import PersonService

person = PersonService.create_person(
    pib = "Іванов Іван Іванович",
    rank = "Солдат",
    birth_date = "01.01.1990",
    position = "Оператор",
    phone = "+1234567890",
    status = "active"
)

print(f"Person created: {person.pib}, Rank: {person.rank}, Birth Date: {person.birth_date}, Position: {person.position}, Phone: {person.phone}, Status: {person.status}")