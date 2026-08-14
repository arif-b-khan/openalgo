using System.Text.Json;
using OpenAlgo.NET.Models.Responses;

namespace OpenAlgo.NET.Tests;

public class AccountResponseDeserializationTests
{
    [Fact]
    public void FundsResponseAcceptsNumericAccountValues()
    {
        const string json = """
            {
              "data": {
                "availablecash": 9987599.73,
                "collateral": 0.0,
                "m2mrealized": 0.0,
                "m2munrealized": -441.64,
                "utiliseddebits": 12522.22
              },
              "status": "success"
            }
            """;

        var response = TestApi.Deserialize<FundsResponse>(json);

        Assert.True(response.IsSuccess);
        Assert.Equal("9987599.73", response.Data?.AvailableCash);
        Assert.Equal("-441.64", response.Data?.M2MUnrealized);
    }

    [Fact]
    public void OrderBookResponseAcceptsNumericQuantities()
    {
        const string json = """
            {
              "data": {
                "orders": [
                  {
                    "orderid": "123",
                    "quantity": 65,
                    "price": 93.85,
                    "order_status": "complete"
                  }
                ]
              },
              "status": "success"
            }
            """;

        var response = TestApi.Deserialize<OrderBookResponse>(json);

        Assert.True(response.IsSuccess);
        Assert.Equal("65", response.Data?.Orders?[0].Quantity);
        Assert.Equal(93.85m, response.Data?.Orders?[0].Price);
    }

    private sealed class TestApi : OpenAlgo.NET.BaseApi
    {
        private TestApi()
            : base("test-key")
        {
        }

        public static T Deserialize<T>(string json)
            where T : class, new()
        {
            return JsonSerializer.Deserialize<T>(json, JsonOptions)
                ?? throw new InvalidOperationException("Expected a response.");
        }
    }
}
